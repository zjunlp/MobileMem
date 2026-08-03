import uuid 
import os 
import json 
import pickle 
from collections import deque 
from langchain.embeddings import init_embeddings
from langgraph.store.memory import InMemoryStore
from ._mixin import MessageBufferMixin 
from .base import MemBaseLayer
from ..configs.naive_rag import NaiveRAGConfig
from ..model_types.memory import MemoryEntry
from ..model_types.dataset import Message
from typing import Any, ClassVar


class NaiveRAGLayer(MemBaseLayer, MessageBufferMixin):

    layer_type: ClassVar[str] = "NaiveRAG"

    def __init__(self, config: NaiveRAGConfig) -> None:
        """Create an interface of naive RAG. The implementation is based on the 
        third-party library `langchain`."""
        self._init_buffer(
            num_overlap_msgs=config.num_overlap_msgs,
            max_tokens=config.max_tokens,
            model_for_tokenizer=config.llm_model,
            deferred=config.deferred,
        )
        self.memory_layer = InMemoryStore(
            index={
                "dims": config.retriever_dim, 
                "embed": init_embeddings(
                    config.retriever_name_or_path,
                    **config.embedding_kwargs,
                ), 
                "fields": ["content"],   
            }, 
        ) 
        self.config = config

        # Store each memory unit's id.
        self._memory_ids = set() 
    
    def get_namespace(self) -> tuple[str, str]:
        """Get the namespace of the memory layer.
        
        Returns:
            tuple[str, str]: 
                A tuple containing the namespace prefix and the user identifier.
        """
        return ("memories", self.config.user_id)

    def add_message(self, message: Message, **kwargs: Any) -> None:
        text = f"Speaker {message.name} (role: {message.role}) says: {message.content}\nTimestamp: {message.timestamp}"

        # Add the current message into the buffer and get the document to index.
        doc = self._buffer_and_get_doc(
            message_content=text,
            separator=self.config.message_separator,
        )
        if doc is not None:
            # Index the document into naive RAG.
            mem_id = str(uuid.uuid4())
            # Build metadata containing images
            value = {
                "content": doc
            }
            if message.images:
                value["image_path"] = message.images

            # print(value)
            self.memory_layer.put(self.get_namespace(), mem_id, value)
            self._memory_ids.add(mem_id)

    def add_messages(self, messages: list[Message], **kwargs: Any) -> None:
        for message in messages:
            self.add_message(message, **kwargs)

    def retrieve(self, query: str, k: int = 10, **kwargs: Any) -> list[MemoryEntry]:
        # It returns a list of `SearchItem` objects.
        # See https://reference.langchain.com/python/langgraph-sdk/schema/SearchItem.
        memories = self.memory_layer.search(
            self.get_namespace(),
            query=query,
            limit=k,
            **kwargs,
        )
        outputs = []
        for memory in memories:
            memory_dict = memory.dict()         
            # print(memory_dict)
            content = memory_dict["value"]["content"]
            metadata = {
                key: value
                for key, value in memory_dict.items() if key != "value"
            }
            # Check whether a metadata field exists
            nested_metadata = memory_dict.get("value", {})
            parts = [f"Memory: {content}"]
            if nested_metadata.get("image_path"):
                parts.append(f"\n[Images attached: {len(nested_metadata['image_path'])}]")
            formatted = "\n".join(parts)

            outputs.append(
                MemoryEntry(
                    content=content,
                    formatted_content=formatted,
                    metadata=metadata,
                    image_path=nested_metadata.get("image_path"),
                )
            )
        return outputs

    def delete(self, memory_id: str) -> bool:
        namespace = self.get_namespace()

        item = self.memory_layer.get(namespace, memory_id)
        if item is None:
            return False

        # TODO: The message buffer is synchronized with deletion operations.
        try:
            self.memory_layer.delete(namespace, memory_id)
            self._memory_ids.remove(memory_id)
            return True
        except Exception as e:
            print(f"Error in delete method in NaiveRAGLayer: \n\t{e.__class__.__name__}: {e}")
            return False

    def update(self, memory_id: str, **kwargs) -> bool:
        namespace = self.get_namespace()

        item = self.memory_layer.get(namespace, memory_id)
        if item is None:
            return False

        # Existing fields in the memory unit are overwritten by matching
        # keys in `kwargs`. Extra keys in `kwargs` are added as new fields.
        # TODO: The message buffer is synchronized with update operations.
        new_value = {
            **item.value,
            **kwargs, 
        }        
        try:
            self.memory_layer.put(
                namespace, 
                memory_id,
                new_value,
            ) 
            return True
        except Exception as e:
            print(f"Error in update method in NaiveRAGLayer: \n\t{e.__class__.__name__}: {e}")
            return False

    def load_memory(self, user_id: str | None = None) -> bool:
        if user_id is None:
            user_id = self.config.user_id
        pkl_path = os.path.join(self.config.save_dir, f"{user_id}.pkl")
        config_path = os.path.join(self.config.save_dir, "config.json")
        buffer_path = os.path.join(self.config.save_dir, "buffer_state.json") 
        if (
            not os.path.exists(pkl_path) or 
            not os.path.exists(config_path) or 
            not os.path.exists(buffer_path)
        ):
            return False 
        
        with open(config_path, "r", encoding="utf-8") as f:
            config_dict = json.load(f)
        if user_id != config_dict["user_id"]:
            raise ValueError(
                f"The user id in the config file ({config_dict['user_id']}) "
                f"does not match the user id ({user_id}) in the function call."
            )
            
        config = NaiveRAGConfig(**config_dict)
        self._init_buffer(
            num_overlap_msgs=config.num_overlap_msgs,
            max_tokens=config.max_tokens,
            model_for_tokenizer=config.llm_model,
            deferred=config.deferred,
        )
        self.memory_layer = InMemoryStore(
            index={
                "dims": config.retriever_dim, 
                "embed": init_embeddings(
                    config.retriever_name_or_path,
                    **config.embedding_kwargs,
                ), 
                "fields": ["content"],   
            }, 
        ) 

        with open(buffer_path, "r", encoding="utf-8") as f:
            buffer_state = json.load(f)
        self._message_buffer = deque(buffer_state["message_buffer"])
        self._buffer_total_tokens = buffer_state["buffer_total_tokens"]

        with open(pkl_path, "rb") as f:
            predefined_memory_units = pickle.load(f)

        self._memory_ids.clear()
        self.config = config 
        namespace = self.get_namespace()
        for memory_unit in predefined_memory_units:
            self.memory_layer.put(
                namespace, 
                **memory_unit
            ) 
            self._memory_ids.add(memory_unit["key"])

        return True 

    def save_memory(self) -> None:
        os.makedirs(self.config.save_dir, exist_ok=True)

        # Save layer config.
        config_path = os.path.join(self.config.save_dir, "config.json")
        config_dict = {
            "layer_type": self.layer_type,
            **self.config.model_dump()
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=4)

        buffer_path = os.path.join(self.config.save_dir, "buffer_state.json")
        buffer_state = {
            "message_buffer": list(self._message_buffer),
            "buffer_total_tokens": self._buffer_total_tokens,
        }
        with open(buffer_path, "w", encoding="utf-8") as f:
            json.dump(
                buffer_state, 
                f, 
                ensure_ascii=False,
                indent=4,
            )

        # In NaiveRAG, we don't store the vector embeddings. 
        preserved_memory_units = [] 
        namespace = self.get_namespace()
        for memory_id in self._memory_ids: 
            item = self.memory_layer.get(namespace, memory_id)
            if item is not None:
                preserved_memory_units.append(
                    {
                        "key": memory_id,
                        "value": item.value,
                    }
                )

        pkl_path = os.path.join(self.config.save_dir, f"{self.config.user_id}.pkl")
        with open(pkl_path, "wb") as f:
            pickle.dump(preserved_memory_units, f)

    def flush(self) -> None:
        doc = self._flush_buffer(separator=self.config.message_separator)
        if doc is not None:
            mem_id = str(uuid.uuid4())
            value = {
                "content": doc, 
            }
            self.memory_layer.put(self.get_namespace(), mem_id, value) 
            self._memory_ids.add(mem_id)
