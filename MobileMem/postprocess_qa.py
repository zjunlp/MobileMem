# -*- coding: utf-8 -*-
"""Post-process question-answer pairs."""
import argparse
import asyncio
import json
import os
import random
import signal
from typing import Any

import shortuuid
from pydantic import BaseModel, Field
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg, TextBlock
from agentscope.model import OpenAIChatModel
from agentscope.rag import (
    SimpleKnowledge,
    Document, 
    DocMetadata, 
    MilvusLiteStore,
)
from agentscope.embedding import OpenAITextEmbedding

from keme.models import QuestionAnswerPair, QuestionTypeToolbook
from keme.toolkits import SynthesisAgent


_REVISION_SYSTEM_PROMPT = (
    "You are an expert at revising question-answer pairs for AI memory system evaluation. "
    "Your task is to analyze question-answer pairs and revise them when necessary to ensure "
    "quality, diversity, and answerability."
)

_REVISION_TASK_PROMPT = (
    "## Question Type Description\n\n"
    "{question_type_description}\n\n"
    "## Current Question-Answer Pair\n\n"
    "{current_qa_pair}\n\n"
    "## Similar Question-Answer Pairs\n\n"
    "{similar_qa_pairs}\n\n"
    "## Task\n\n"
    "Please analyze the current question-answer pair and determine whether it needs revision. "
    "Consider the following criteria:\n\n"
    "1. **Semantic Similarity**: If the current question is too similar to an existing question, "
    "revise it to test a different aspect of the same information. For example, if both questions "
    "ask 'What family rules did the user establish with their wife at Christmas?', one could be "
    "revised to 'Who established family rules with the user at Christmas?'\n\n"
    "2. **Answerability**: For unanswerable questions, you do not need to consider this criterion. "
    "For answerable questions, you need to check if the source evidences contain sufficient information "
    "to answer the question. If not, the question or answer must be revised to be answerable based on "
    "the available source evidences.\n\n"
    "3. **Temporal Reference**: If the question contains phrases like 'this discussion', 'this conversation', "
    "or 'this session', revise them to 'previous discussion', 'previous conversation', or 'previous session' "
    "to avoid ambiguity when the question is used in a different context.\n\n"
    "4. **Answer Leakage**: If the question directly reveals or strongly hints at the "
    "answer (e.g., it already summarizes the evidence and then asks the model to 'conclude' or 'summarize'), "
    "revise the question-answer pair to remove the leaked answer. The revised question should ask for the "
    "information without embedding the conclusion. For example, revise a leading question like "
    "'Based on the user often shopping and buying many electronic products on Singles' Day, please summarize "
    "the user's shopping preferences.' into a neutral form that does not pre-state the preference.\n\n"
    "5. **Constraints**: You MUST preserve the question type and question form. Only the question "
    "and answer can be modified.\n\n"
    "Please provide your analysis and revision decision."
)


class RevisionResult(BaseModel):
    """Structured output for question-answer pair revision."""
    
    need_refined: bool = Field(
        ...,
        description=(
            "Whether the question-answer pair needs to be refined. "
            "Set to `True` if the question is too similar to existing ones or "
            "if the source evidences cannot answer the current question. "
            "Set to `False` if no revision is needed."
        ),
    )
    question: str = Field(
        ...,
        description=(
            "The revised question text. If `need_refined` is `False`, this should be "
            "the same as the original question. If `True`, this should be the revised "
            "question that tests a different aspect or is answerable by the source evidences."
        ),
    )
    answer: str = Field(
        ...,
        description=(
            "The revised answer text. If `need_refined` is `False`, this should be "
            "the same as the original answer. If `True`, this should be the revised "
            "answer that corresponds to the revised question and is supported by the source evidences."
        ),
    )
    explanation: str = Field(
        default="",
        description=(
            "Your reasoning process for determining whether and how to revise the "
            "question-answer pair. Explain why you reached your conclusion."
        ),
    )


class QAPostprocessor:
    """Post-processor for question-answer pairs."""
    
    def __init__(self, args: argparse.Namespace) -> None:
        """Initialize the question-answer pair post-processor.
        
        Args:
            args (`argparse.Namespace`):
                Parsed command line arguments.
        """
        self.args = args
        self.task_cancelled = False
        
        self.knowledge = None
        self.agent_kwargs = {}
        self.toolbook = None
        
        signal.signal(signal.SIGINT, self._signal_handler)
        self.stats = {
            "total_qa_pairs": 0,
            "revised_qa_pairs": 0,
            "skipped_qa_pairs": 0,
            "failed_qa_pairs": 0,
        }
    
    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle Ctrl+C signals."""
        if not self.task_cancelled:
            print("\n⚠️  Post-processing cancelled.")
            self.task_cancelled = True
            try:
                loop = asyncio.get_running_loop()
                for task in asyncio.all_tasks(loop):
                    if not task.done():
                        task.cancel()
            except RuntimeError:
                pass
        else:
            os._exit(0)
    
    def _setup_model(self) -> dict[str, Any]:
        """Set up the model and return agent keyword arguments.
        
        Returns:
            `dict[str, Any]`:
                Keyword arguments for the synthesis agent.
        """
        api_key = self.args.api_key or os.environ.get("OPENAI_API_KEY")
        api_base = self.args.api_base or os.environ.get("OPENAI_API_BASE")
        
        if not api_key:
            raise ValueError(
                "OpenAI API key is required. Provide via --api_key or OPENAI_API_KEY environment variable."
            )
        
        client_args = {}
        if api_base:
            client_args["base_url"] = api_base
        
        model = OpenAIChatModel(
            model_name=self.args.model,
            api_key=api_key,
            client_args=client_args,
            generate_kwargs={
                "temperature": self.args.temperature,
            },
        )
        
        print(f"✅ Model configured: {self.args.model}")
        print(f"   - Temperature: {self.args.temperature}")
        
        return {
            "model": model,
            "formatter": OpenAIChatFormatter(),
            "max_iters": self.args.max_iters,
        }
    
    def _setup_embedding_model(self) -> OpenAITextEmbedding:
        """Set up the embedding model.
        
        Returns:
            `OpenAITextEmbedding`:
                The configured embedding model.
        """
        api_key = self.args.embedding_api_key or self.args.api_key or os.environ.get("OPENAI_API_KEY")
        api_base = self.args.embedding_api_base or self.args.api_base or os.environ.get("OPENAI_API_BASE")
        
        if not api_key:
            raise ValueError(
                "OpenAI API key is required for embeddings. "
                "Provide via --embedding_api_key, --api_key, or OPENAI_API_KEY environment variable."
            )
        
        kwargs = {}
        if api_base:
            kwargs["base_url"] = api_base
        
        embedding_model = OpenAITextEmbedding(
            api_key=api_key,
            model_name=self.args.embedding_model,
            dimensions=self.args.embedding_dimensions,
            **kwargs,
        )
        
        print(f"✅ Embedding model configured: {self.args.embedding_model}")
        print(f"   - Dimensions: {self.args.embedding_dimensions}")
        
        return embedding_model
    
    def _setup_vector_store(self) -> MilvusLiteStore:
        """Set up the vector store.
        
        Returns:
            `MilvusLiteStore`:
                The configured vector store.
        """
        store = MilvusLiteStore(
            uri=self.args.milvus_uri,
            collection_name=self.args.collection_name,
            dimensions=self.args.embedding_dimensions,
            distance=self.args.distance_metric,
        )

        client = store.get_client()
        kwargs = {
            "collection_name": store.collection_name,
            "dimension": store.dimensions,
            "metric_type": store.distance,
            **store.collection_kwargs,
        }
        client.create_collection(**kwargs)
        
        print(f"✅ Vector store configured: {self.args.milvus_uri}")
        print(f"   - Collection: {self.args.collection_name}")
        print(f"   - Distance metric: {self.args.distance_metric}")
        
        return store
    
    def _load_input_data(self) -> dict[str, Any]:
        """Load the input JSON file generated by run_qa_synthesis.py.
        
        Returns:
            `dict[str, Any]`:
                The loaded data containing QA pairs and toolbook.
        """
        if not os.path.exists(self.args.input_path):
            raise FileNotFoundError(
                f"Input file '{self.args.input_path}' not found. "
                "Please provide a valid QA synthesis results file."
            )
        
        with open(self.args.input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        print(f"✅ Loaded input file: {self.args.input_path}")
        
        return data
    
    def _extract_qa_pairs_from_toolbook(
        self,
        toolbook_data: dict[str, Any],
    ) -> list[QuestionAnswerPair]:
        """Extract question-answer pairs from the question type toolbook data.
        
        Args:
            toolbook_data (`dict[str, Any]`):
                The toolbook data from the input file.
        
        Returns:
            `list[QuestionAnswerPair]`:
                The list of question-answer pairs extracted from the toolbook.
        """
        self.toolbook = QuestionTypeToolbook.model_validate(toolbook_data)
        qa_pairs = []
        for qtype in self.toolbook.question_types:
            qa_pairs.extend(qtype.qa_pairs)
        return qa_pairs
    
    def _get_question_type_description(self, question_type: str) -> str:
        """Get the description for a question type.
        
        Args:
            question_type (`str`):
                The name of the question type.
        
        Returns:
            `str`:
                The description of the question type.
        """
        if self.toolbook is None:
            return "[THE DESCRIPTION OF THIS QUESTION TYPE IS NOT AVAILABLE]"
        
        qtype = self.toolbook.get_question_type(question_type)
        if qtype is None:
            return "[THE DESCRIPTION OF THIS QUESTION TYPE IS NOT AVAILABLE]"
        
        return f"{qtype.name}: {qtype.description}"

    def _format_qa_for_knowledge_base(self, qa_pair: QuestionAnswerPair) -> str:
        """Format a question-answer pair for storage in the knowledge base.
        
        Args:
            qa_pair (`QuestionAnswerPair`):
                The question-answer pair to format.
        
        Returns:
            `str`:
                The formatted string for the vector store.
        """
        answer_str = qa_pair.golden_answers[0]
        return f"Question: {qa_pair.question}\nAnswer: {answer_str}"

    async def _add_qa_to_knowledge_base(
        self,
        qa_pair: QuestionAnswerPair,
        chunk_id: int,
        total_chunks: int,
    ) -> None:
        """Add a single question-answer pair to the knowledge base.
        
        Args:
            qa_pair (`QuestionAnswerPair`):
                The question-answer pair to add.
            chunk_id (`int`):
                The chunk ID for this document.
            total_chunks (`int`):
                The total number of chunks.
        """
        content_text = self._format_qa_for_knowledge_base(qa_pair)
        doc = Document(
            id=qa_pair.id,
            metadata=DocMetadata(
                content=TextBlock(type="text", text=content_text),
                doc_id=qa_pair.id,
                chunk_id=chunk_id,
                total_chunks=total_chunks,
            ),
        )
        await self.knowledge.add_documents([doc])

    async def revise_question_answer_pair(
        self,
        qa_pair: QuestionAnswerPair,
    ) -> tuple[QuestionAnswerPair, RevisionResult]:
        """Revise a question-answer pair based on semantic similarity and answerability.
        
        This method retrieves semantically similar questions from the knowledge base,
        checks if the current question-answer pair needs revision, and uses an LLM to revise it if necessary.
        
        Args:
            qa_pair (`QuestionAnswerPair`):
                The question-answer pair to potentially revise.
        
        Returns:
            `tuple[QuestionAnswerPair, RevisionResult]`:
                A tuple containing the (potentially revised) question-answer pair and the revision result.
        """
        # Retrieve similar QA pairs from the knowledge base
        similar_docs = await self.knowledge.retrieve(
            query=self._format_qa_for_knowledge_base(qa_pair),
            limit=self.args.top_k,
            score_threshold=self.args.similarity_threshold,
        )
        
        if similar_docs:
            similar_qa_pairs_str = "\n".join(
                f"- {doc.metadata.content['text']}"
                for doc in similar_docs
            )
        else:
            similar_qa_pairs_str = "[NO SIMILAR QUESTION-ANSWER PAIRS ARE AVAILABLE]"
        
        current_qa_str = qa_pair.to_markdown(
            include_evidences=True,
            include_side_note=True,
            level=0,
        )
        question_type_desc = self._get_question_type_description(qa_pair.question_type)
        
        # Create the revision agent
        revision_agent_kwargs = {**self.agent_kwargs}
        revision_agent_kwargs["name"] = f"revision_agent_{shortuuid.uuid()}"
        revision_agent_kwargs["sys_prompt"] = _REVISION_SYSTEM_PROMPT
        revision_agent = SynthesisAgent(**revision_agent_kwargs)

        response_msg = await revision_agent(
            msg=Msg(
                "user",
                _REVISION_TASK_PROMPT.format(
                    question_type_description=question_type_desc,
                    current_qa_pair=current_qa_str,
                    similar_qa_pairs=similar_qa_pairs_str,
                ),
                "user",
            ),
            structured_model=RevisionResult,
        )
        revision_result = RevisionResult.model_validate(response_msg.metadata)
        
        # Apply revision if needed
        if revision_result.need_refined:
            # Create a new QA pair with revised question and answer
            # Preserve other metadata
            revised_qa_data = qa_pair.model_dump()
            revised_qa_data["question"] = revision_result.question
            revised_qa_data["golden_answers"] = [revision_result.answer]
            revised_qa_data["id"] = f"qa_{shortuuid.uuid()}"
            revised_qa_pair = QuestionAnswerPair.model_validate(revised_qa_data)
            return revised_qa_pair, revision_result
        
        return qa_pair, revision_result
    
    async def run(self) -> None:
        """Run the post-processing pipeline."""
        print("\n" + "=" * 60)
        print("KEME: Question-Answer Pairs Post-Processing")
        print("=" * 60 + "\n")
        
        # Load input data
        data = self._load_input_data()
        
        # Set up model and embedding
        self.agent_kwargs = self._setup_model()
        embedding_model = self._setup_embedding_model()
        vector_store = self._setup_vector_store()
        
        # Build an empty knowledge base
        self.knowledge = SimpleKnowledge(
            embedding_store=vector_store,
            embedding_model=embedding_model,
        )
        
        # Extract question-answer pairs from the toolbook
        qa_pairs = self._extract_qa_pairs_from_toolbook(data["question_type_toolbook"])
        self.stats["total_qa_pairs"] = len(qa_pairs)
        
        print(f"\n✅ Found {len(qa_pairs)} QA pairs to process")
        
        # Shuffle question-answer pairs for randomized processing order
        random.seed(self.args.random_seed)
        shuffled_qa_pairs = qa_pairs.copy()
        random.shuffle(shuffled_qa_pairs)
        
        print(f"✅ Shuffled QA pairs with random seed: {self.args.random_seed}")
        
        print("\n" + "=" * 60)
        print("🚀 Starting post-processing...")
        print("=" * 60 + "\n")
        
        revised_qa_pairs = []
        revision_results = []
        
        try:
            for i, qa_pair in enumerate(shuffled_qa_pairs):
                if self.task_cancelled:
                    break
                
                print(f"[{i + 1}/{len(shuffled_qa_pairs)}] Processing: {qa_pair.question[:50]}...")
                
                try:
                    # Revise the QA pair
                    revised_qa, result = await self.revise_question_answer_pair(qa_pair)
                    
                    revised_qa_pairs.append(revised_qa)
                    revision_results.append(
                        {
                            "original_id": qa_pair.id,
                            "revised_id": revised_qa.id,
                            "need_refined": result.need_refined,
                            "explanation": result.explanation,
                        }
                    )
                    
                    if result.need_refined:
                        self.stats["revised_qa_pairs"] += 1
                        print(f"   ✓ Revised: {result.question}...")
                    else:
                        print(f"   ✓ No revision needed")
                    
                    # Add the (revised) QA pair to the knowledge base for future comparisons
                    await self._add_qa_to_knowledge_base(
                        qa_pair=revised_qa,
                        chunk_id=i,
                        total_chunks=len(shuffled_qa_pairs),
                    )
                    
                except Exception as e:
                    print(f"   ✗ Failed: {str(e)}")
                    self.stats["failed_qa_pairs"] += 1
                    revised_qa_pairs.append(qa_pair)  # Keep original on failure
                    revision_results.append(
                        {
                            "original_id": qa_pair.id,
                            "revised_id": qa_pair.id,
                            "need_refined": False,
                            "explanation": f"Failed to process: {str(e)}",
                        }
                    )
        
        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            pass
        
        # Save results
        new_toolbook = self.toolbook.model_dump()
        for qtype in new_toolbook["question_types"]:
            qtype["qa_pairs"].clear()
        new_toolbook = QuestionTypeToolbook.model_validate(new_toolbook)
        for qa_pair in revised_qa_pairs:
            new_toolbook.register_qa_pair(qa_pair)

        output_data = {
            "person": data.get("person"),
            "sessions": data.get("sessions", []),
            "graphs": data.get("graphs", []),
            "old_question_type_toolbook": data.get("question_type_toolbook"),
            "question_type_toolbook": new_toolbook.model_dump(),
            "revised_qa_pairs": [
                qa.model_dump() for qa in revised_qa_pairs
            ],
            "revision_results": revision_results,
            "statistics": self.stats,
        }
        
        with open(self.args.output_path, "w", encoding="utf-8") as f:
            json.dump(
                output_data, 
                f, 
                ensure_ascii=False, 
                indent=4,
            )
        
        print(f"\n💾 Results saved to {self.args.output_path}")
        
        # Print summary
        print("\n" + "=" * 60)
        if self.task_cancelled:
            print("⏸️  Post-processing cancelled")
        else:
            print("✅ Post-processing complete")
        print("=" * 60)
        print(f"   Total QA pairs: {self.stats['total_qa_pairs']}")
        print(f"   Revised: {self.stats['revised_qa_pairs']}")
        print(f"   Failed: {self.stats['failed_qa_pairs']}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Post-process QA pairs generated by run_qa_synthesis.py.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # Input/Output configuration
    parser.add_argument(
        "--input_path",
        type=str,
        default="qa_synthesis_results.json",
        help="Path to the questiona-answer pair synthesis results JSON file.",
    )
    parser.add_argument(
        "--output_path",
        type=str,
        default="qa_postprocessed_results.json",
        help="Path to save the post-processed results.",
    )
    
    # Model configuration
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5.1",
        help="Model name for revision agent.",
    )
    parser.add_argument(
        "--api_key",
        type=str,
        default=None,
        help="OpenAI API key. If not provided, uses OPENAI_API_KEY environment variable.",
    )
    parser.add_argument(
        "--api_base",
        type=str,
        default=None,
        help="OpenAI API base URL. If not provided, uses OPENAI_API_BASE environment variable.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Temperature for model generation.",
    )
    parser.add_argument(
        "--max_iters",
        type=int,
        default=10,
        help="Maximum iterations for the revision agent.",
    )
    
    # Embedding configuration
    parser.add_argument(
        "--embedding_model",
        type=str,
        default="text-embedding-3-small",
        help="Embedding model name for semantic similarity.",
    )
    parser.add_argument(
        "--embedding_api_key",
        type=str,
        default=None,
        help="API key for embedding model. If not provided, uses --api_key.",
    )
    parser.add_argument(
        "--embedding_api_base",
        type=str,
        default=None,
        help="API base URL for embedding model. If not provided, uses --api_base.",
    )
    parser.add_argument(
        "--embedding_dimensions",
        type=int,
        default=1024,
        help="Embedding vector dimensions.",
    )
    
    # Vector store configuration
    parser.add_argument(
        "--milvus_uri",
        type=str,
        default="./qa_postprocess_milvus.db",
        help="URI for Milvus Lite database (local file path for local mode).",
    )
    parser.add_argument(
        "--collection_name",
        type=str,
        default="qa_questions",
        help="Milvus collection name for storing question embeddings.",
    )
    parser.add_argument(
        "--distance_metric",
        type=str,
        default="COSINE",
        choices=["COSINE", "L2", "IP"],
        help="Distance metric for vector similarity search.",
    )
    
    # Similarity retrieval configuration
    parser.add_argument(
        "--similarity_threshold",
        type=float,
        default=None,
        help="Similarity score threshold for detecting similar questions. If None, no threshold is applied.",
    )
    parser.add_argument(
        "--top_k",
        type=int,
        default=5,
        help="Number of similar questions to retrieve for comparison.",
    )
    
    # Random seed
    parser.add_argument(
        "--random_seed",
        type=int,
        default=42,
        help="Random seed for shuffling QA pairs.",
    )
    
    return parser.parse_args()


async def main() -> None:
    """Main entry point."""
    args = parse_args()
    postprocessor = QAPostprocessor(args)
    await postprocessor.run()


if __name__ == "__main__":
    asyncio.run(main())
