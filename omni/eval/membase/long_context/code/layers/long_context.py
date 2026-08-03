import os
import json
from collections import deque
from .base import MemBaseLayer
from ._mixin import MessageBufferMixin
from ..configs.long_context import LongContextConfig
from ..model_types.memory import MemoryEntry
from ..model_types.dataset import Message
from typing import Any, ClassVar


class LongContextLayer(MemBaseLayer, MessageBufferMixin):

    layer_type: ClassVar[str] = "Long-Context"

    def __init__(self, config: LongContextConfig) -> None:
        """Create an interface of the online long-context memory layer."""
        self._init_buffer(
            num_overlap_msgs=float("inf"),
            max_tokens=config.context_window,
            model_for_tokenizer=config.llm_model,
            deferred=False, 
        )
        self.config = config
        # parallel buffer to store images/captions aligned with message buffer
        from collections import deque as _dq
        self._images_buffer = _dq()

    def add_message(self, message: Message, **kwargs: Any) -> None:
        text = f"Speaker {message.name} (role: {message.role}) says: {message.content}\nTimestamp: {message.timestamp}"
        # Append to the text buffer
        self._buffer_and_get_doc(
            message_content=text,
            separator=self.config.message_separator,
        )
        # keep parallel image records aligned with message buffer
        images_info = {}
        if message.images:
            images_info["image_path"] = message.images
        self._images_buffer.append(images_info)
        # Trim images buffer to match message buffer size
        while len(self._images_buffer) > len(self._message_buffer):
            self._images_buffer.popleft()

    def add_messages(self, messages: list[Message], **kwargs: Any) -> None:
        for message in messages:
            self.add_message(message, **kwargs)

    def retrieve(self, query: str, k: int = 10, **kwargs: Any) -> list[MemoryEntry]:
        # For the long-context baseline, we only return the history as the memory.
        # The total number of retrieved memories is always 1.
        # Therefore, `k` is ignored.
        history = self._buffer_and_get_doc()
        formatted_history = (
            "The following content enclosed in <long_context_memory> tags is the user's "
            "historical interaction trajectory so far:\n"
            f"<long_context_memory>\n{history}\n</long_context_memory>\n"
            "This interaction trajectory is your long-term memory."
        )
        # Collect image paths from parallel image buffer
        collected_paths = []
        for info in list(self._images_buffer):
            if not info:
                continue
            if info.get("image_path"):
                collected_paths.extend(info.get("image_path") or [])

        # Build formatted content to list attached images (count only).
        formatted_parts = [formatted_history]
        if collected_paths:
            formatted_parts.append(f"\n[Images attached: {len(collected_paths)}]")

        formatted_with_images = "".join(formatted_parts)

        return [
            MemoryEntry(
                content=history,
                formatted_content=formatted_with_images,
                image_path=(collected_paths or None),
            )
        ]

    def delete(self, memory_id: str) -> bool:
        raise NotImplementedError(
            "Long-Context (online version) does not support deleting existing memories. "
            "We assume the size of the long-context memory is 1."
        )

    def update(self, memory_id: str, **kwargs) -> bool:
        raise NotImplementedError(
            "Long-Context (online version) does not support updating existing memories. "
            "We assume the size of the long-context memory is 1."
        )

    def save_memory(self) -> None:
        os.makedirs(self.config.save_dir, exist_ok=True)

        config_path = os.path.join(self.config.save_dir, "config.json")
        config_dict = {
            "layer_type": self.layer_type,
            **self.config.model_dump()
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=4)

        # The buffer state represents the long-context memory.
        buffer_path = os.path.join(self.config.save_dir, "buffer_state.json")
        buffer_state = {
            "message_buffer": list(self._message_buffer),
            "buffer_total_tokens": self._buffer_total_tokens,
            "images_buffer": list(self._images_buffer),
        }
        with open(buffer_path, "w", encoding="utf-8") as f:
            json.dump(
                buffer_state, 
                f, 
                ensure_ascii=False,
                indent=4,
            )

    def load_memory(self, user_id: str | None = None) -> bool:
        if user_id is None:
            user_id = self.config.user_id
        
        config_path = os.path.join(self.config.save_dir, "config.json")
        buffer_path = os.path.join(self.config.save_dir, "buffer_state.json")
        
        if not os.path.exists(config_path) or not os.path.exists(buffer_path):
            return False
        
        with open(config_path, "r", encoding="utf-8") as f:
            config_dict = json.load(f)
        if user_id != config_dict["user_id"]:
            raise ValueError(
                f"The user id in the config file ({config_dict['user_id']}) "
                f"does not match the user id ({user_id}) in the function call."
            )

        config = LongContextConfig(**config_dict)
        self._init_buffer(
            num_overlap_msgs=float("inf"),
            max_tokens=config.context_window,
            model_for_tokenizer=config.llm_model,
            deferred=False, 
        )

        with open(buffer_path, "r", encoding="utf-8") as f:
            buffer_state = json.load(f)
        self._message_buffer = deque(buffer_state["message_buffer"])
        self._buffer_total_tokens = buffer_state["buffer_total_tokens"]
        self._images_buffer = deque(buffer_state.get("images_buffer", []))

        self.config = config
        return True
