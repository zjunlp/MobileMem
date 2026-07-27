import os

from ..utils import PatchSpec, make_attr_patch
os.environ["MEM0_TELEMETRY"] = "False" # Disable telemetry.

import json
from mem0 import Memory
from mem0.configs.base import MemoryConfig
from mem0.memory.storage import SQLiteManager
from mem0.utils.factory import (
    EmbedderFactory,
    GraphStoreFactory,
    LlmFactory,
    VectorStoreFactory,
    RerankerFactory,
)
from .base import MemBaseLayer
from ..utils import (
    token_monitor,
)
from ..configs.mem0 import Mem0Config
from ..model_types.memory import MemoryEntry
from ..model_types.dataset import Message
from typing import Any, ClassVar


class Mem0Memory(Memory):
    """A thin subclass of ``mem0.Memory`` that skips telemetry initialization.

    The upstream ``Memory.__init__`` creates an additional Qdrant collection
    (``mem0migrations``) solely for anonymous usage telemetry via PostHog.
    This is unnecessary for evaluation and introduces extra I/O and potential
    lock contention when running multiple instances in parallel."""

    def __init__(self, config: MemoryConfig = MemoryConfig()) -> None:
        self.config = config

        self.custom_fact_extraction_prompt = self.config.custom_fact_extraction_prompt
        self.custom_update_memory_prompt = self.config.custom_update_memory_prompt
        self.embedding_model = EmbedderFactory.create(
            self.config.embedder.provider,
            self.config.embedder.config,
            self.config.vector_store.config,
        )
        self.vector_store = VectorStoreFactory.create(
            self.config.vector_store.provider, 
            self.config.vector_store.config,
        )
        self.llm = LlmFactory.create(
            self.config.llm.provider, 
            self.config.llm.config,
        )
        self.db = SQLiteManager(self.config.history_db_path)
        self.collection_name = self.config.vector_store.config.collection_name
        self.api_version = self.config.version

        # Initialize reranker if configured.
        self.reranker = None
        if config.reranker:
            self.reranker = RerankerFactory.create(
                config.reranker.provider,
                config.reranker.config,
            )

        self.enable_graph = False

        if self.config.graph_store.config:
            provider = self.config.graph_store.provider
            self.graph = GraphStoreFactory.create(provider, self.config)
            self.enable_graph = True
        else:
            self.graph = None

        # Telemetry is intentionally skipped. Set the attribute to `None`. 
        self._telemetry_vector_store = None


class Mem0Layer(MemBaseLayer):

    layer_type: ClassVar[str] = "Mem0"

    def __init__(self, config: Mem0Config) -> None:
        """Create an interface of Mem0. The implementation is based on the 
        third-party library `mem0ai`."""
        self._init_layer(config)
        self.config = config

    def _init_layer(self, config: Mem0Config) -> None:
        """Initialize the Mem0 layer.

        Mem0 natively manages persistence via its Qdrant backend (``on_disk=True``), 
        so no additional serialization is required.
        
        Args:
            config (`Mem0Config`): 
                The configuration for the Mem0 layer.
        """
        mem0_config = config.build_mem0_config()
        self.memory_layer = Mem0Memory.from_config(mem0_config)


    def add_message(self, message: Message, **kwargs: Any) -> None:
        text = (
            f"{message.content}\nBelow is this message's metadata:\n"
            f"Speaker Name: {message.name}\n"
            f"Speaker Role: {message.role}\n"
        )
        
        # print("Adding the following message to Mem0Layer:")
        # print(message)
        # 构建包含 images 的元数据
        metadata = {
            "timestamp": message.timestamp,
            "speakers": message.name,
        }
        if message.images:
            metadata["image_path"] = message.images
        try:
            self.memory_layer.add(
                messages=text,
                user_id=self.config.user_id,
                metadata=metadata,
                **kwargs,
            )
        except Exception as e:
            print(f"Error in add_message method in Mem0Layer: \n\t{e.__class__.__name__}: {e}")

    def add_message0(self, message: Message, **kwargs: Any) -> None:
        # Note that Mem0 does't use name field directly. 
        # Therefore, we incorporate the name information into the message content 
        # to retain speaker identity.
        text = (
            f"{message.content}\nBelow is this message's metadata:\n"
            f"Speaker Name: {message.name}\n"
            f"Speaker Role: {message.role}\n"
        )

        # Following Mem0's implementation (https://github.com/mem0ai/mem0/blob/main/evaluation/src/memzero/add.py#L83).
        try:
            self.memory_layer.add(
                messages=text,
                user_id=self.config.user_id,
                metadata={
                    "timestamp": message.timestamp, 
                    "speakers": message.name,
                },
                **kwargs, 
            )
        except Exception as e:
            print(f"Error in add_message method in Mem0Layer: \n\t{e.__class__.__name__}: {e}")

    def add_messages(self, messages: list[Message], **kwargs: Any) -> None:
        print("Adding messages to Mem0 layer:")
        message_level = kwargs.pop("message_level", True)
        if message_level not in [True, False]:
            raise TypeError(
                "`message_level` must be a boolean to indicate whether the messages "
                "are added to the memory layer message by message or as a whole."
            )
        
        if message_level or len(messages) < 2:
            for message in messages:
                self.add_message(message, **kwargs)
        else:
            new_messages = [] 
            for message in messages:
                msg_dict = message.model_dump(mode="python")
                msg_dict["content"] = (
                    f"{message.content}\nBelow is this message's metadata:\n"
                    f"Speaker Name: {message.name}\n"
                    f"Speaker Role: {message.role}\n"
                )
                new_messages.append(msg_dict)
            
            self.memory_layer.add(
                messages=new_messages,
                user_id=self.config.user_id,
                metadata={
                    "timestamp": f"[{messages[0].timestamp}, {messages[-1].timestamp}]",
                    "speakers": ", ".join(
                        sorted(
                            set(
                                [message.name for message in messages]
                            )
                        )
                    ),
                },
                **kwargs, 
            )

    def retrieve(self, query: str, k: int = 10, **kwargs: Any) -> list[MemoryEntry]:
        result = self.memory_layer.search(
            query=query,
            user_id=self.config.user_id,
            limit=k,
            **kwargs,
        )

        memories = result["results"]
        relations = result.get("relations")

        graph_text = ""
        if relations:
            graph_text = "\n".join(
                ["### Graph Relations:"] + [str(rel) for rel in relations]
            )

        outputs = []
        for item in memories:
            print(item)
            content = item["memory"]
            metadata = {k: v for k, v in item.items() if k != "memory"}
            nested_metadata = metadata.get("metadata", {})
            # Extract nested metadata and merge it into top-level metadata
            metadata.update(nested_metadata)
            # 在 formatted_content 中添加图像信息
            parts = [f"Memory: {content}"]
            if metadata.get("image_path"):
                parts.append(f"[Images attached: {len(metadata['image_path'])}]")

            # do not include captions in formatted content; keep captions in `image_cap`
            if graph_text:
                parts.append(graph_text)
            formatted = "\n".join(parts)

            outputs.append(
                MemoryEntry(
                    content=content,
                    metadata=metadata,
                    formatted_content=formatted,
                    image_path=metadata.get("image_path"),
                )
            )
        return outputs

    def delete(self, memory_id: str) -> bool:
        try:
            self.memory_layer.delete(memory_id)
            return True
        except Exception as e:
            print(f"Error in delete method in Mem0Layer: \n\t{e.__class__.__name__}: {e}")
            return False

    def update(self, memory_id: str, **kwargs: Any) -> bool:
        if "data" not in kwargs:
            raise KeyError("`data` is required in `kwargs` for Mem0 layer.")
        data = kwargs.pop("data")
        try:
            self.memory_layer.update(memory_id, data)
            return True
        except Exception as e:
            print(f"Error in update method in Mem0Layer: \n\t{e.__class__.__name__}: {e}")
            return False

    def save_memory(self) -> None:
        os.makedirs(self.config.save_dir, exist_ok=True)

        # Write config.json.
        config_path = os.path.join(self.config.save_dir, "config.json")
        config_dict = {
            "layer_type": self.layer_type,
            **self.config.model_dump(mode="python"),
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=4)

        # The Qdrant vector store (on_disk=True) and the SQLite history DB persist
        # automatically, so no additional serialization is needed here.

    def load_memory(self, user_id: str | None = None) -> bool:
        if user_id is None:
            user_id = self.config.user_id

        config_path = os.path.join(self.config.save_dir, "config.json")
        if not os.path.exists(config_path):
            return False

        with open(config_path, "r", encoding="utf-8") as f:
            config_dict = json.load(f)
        if user_id != config_dict["user_id"]:
            raise ValueError(
                f"The user id in the config file ({config_dict['user_id']}) "
                f"does not match the user id ({user_id}) in the function call."
            )

        config = Mem0Config(**config_dict)

        # Release the existing Qdrant client's file lock before re-initialization.
        self.cleanup()

        self._init_layer(config)
        self.config = config

        # Verify that the Qdrant store actually contains data for this user.
        try:
            existing = self.memory_layer.get_all(user_id=user_id, limit=1)
            memories = existing["results"]
            return len(memories) > 0
        except Exception:
            return False

    def get_patch_specs(self) -> list[PatchSpec]:
        # # See https://github.com/mem0ai/mem0/blob/v1.0.5/mem0/configs/prompts.py#L62.
        # kwargs.get(
        #     "messages", 
        #     args[0] if len(args) > 0 else ""
        # )[0]["content"].startswith(
        #     "You are a Personal Information Organizer"
        # ) 
        # # See https://github.com/mem0ai/mem0/blob/v1.0.5/mem0/configs/prompts.py#L123. 
        # or kwargs.get(
        #     "messages", 
        #     args[0] if len(args) > 0 else ""
        # )[0]["content"].startswith(
        #     "You are an Assistant Information Organizer"
        # )
        # # See https://github.com/mem0ai/mem0/blob/v1.0.5/mem0/memory/main.py#L426. 
        # or kwargs.get(
        #     "messages", 
        #     args[0] if len(args) > 0 else ""
        # )[0]["content"].startswith(
        #     self.config.custom_fact_extraction_prompt
        # ) 
        # # See https://github.com/mem0ai/mem0/blob/v1.0.5/mem0/memory/kuzu_memory.py#L231. 
        # or kwargs.get(
        #     "messages", 
        #     args[0] if len(args) > 0 else ""
        # )[0]["content"].startswith(
        #     "You are a smart assistant who understands entities and their types in a given text"
        # ) 
        # # See https://github.com/mem0ai/mem0/blob/v1.0.5/mem0/memory/kuzu_memory.py#L266. 
        # or (
        #     "You are an advanced algorithm designed to extract structured information " 
        #     "from text to construct knowledge graphs"
        # ) in kwargs.get(
        #     "messages", 
        #     args[0] if len(args) > 0 else ""
        # )[0]["content"]
        getter, setter = make_attr_patch(self.memory_layer.llm, "generate_response")
        spec = PatchSpec(
            name=f"{self.memory_layer.llm.__class__.__name__}.generate_response",
            getter=getter,
            setter=setter,
            wrapper=token_monitor(
                extract_model_name=lambda *args, **kwargs: (
                    self.config.llm_model, 
                    {
                        # See https://github.com/mem0ai/mem0/blob/v1.0.5/mem0/memory/kuzu_memory.py#L235.
                        # The graph version of Mem0 uses tools to extract entities and their relations. 
                        "tools": kwargs.get("tools"),
                    }
                ),
                # The update-memory prompt is easier to identify than the fact-extraction prompt.
                extract_input_dict=lambda *args, **kwargs: {
                    "messages": kwargs.get("messages", args[0] if len(args) > 0 else ""),
                    "metadata": {
                        "op_type": (
                            "update" if (
                                    "The new retrieved facts are mentioned in the triple backticks. " 
                                    "You have to analyze the new retrieved facts and determine whether " 
                                    "these facts should be added, updated, or deleted in the memory."
                                ) in kwargs.get(
                                    "messages", 
                                    args[0] if len(args) > 0 else [{"content": ""}]
                                )[0]["content"]
                            else "generation"
                        )
                    },
                },
                # The result may be a plain string or an OpenAI-compatible message dictionary
                # (e.g., {"role": "assistant", "content": "..."}).
                extract_output_dict=lambda result: {
                    "messages": result if isinstance(result, str) else [
                        {
                            "role": "assistant",
                            **result,
                        }
                    ],
                },
            ),
        )
        return [spec]

    def cleanup(self) -> None:
        """Release the Qdrant local client's exclusive file lock."""
        client = self.memory_layer.vector_store.client
        client.close()
