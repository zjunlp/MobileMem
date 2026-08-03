from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from pathlib import Path
from typing import Literal


class VisualMemoryConfig(BaseModel):
    """Unified configuration for visual memory retrieval during QA.

    Supports switching between 'siglip2' and 'internvideo2' retrievers via retriever_type.
    Only one retriever can be enabled at a time.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    enabled: bool = Field(
        default=False,
        description="Whether to retrieve extra visual memory images during QA.",
    )
    retriever_type: Literal["siglip2", "internvideo2"] = Field(
        default="siglip2",
        description="Which visual retrieval model to use. Only one retriever can be active at a time.",
    )
    image_root: Path = Field(
        default=Path("data/image") ,
        description="Root directory containing the uuid/uid image folders for retrieval.",
    )
    top_k: int = Field(
        default=5,
        description="Number of visual memory images to retrieve per question.",
    )
    batch_size: int = Field(
        default=16,
        description="Batch size used when embedding images for retrieval.",
    )
    rebuild_index: bool = Field(
        default=False,
        description="Force rebuilding image indexes instead of reusing cached ones.",
    )
    device: str = Field(
        default="cuda" if __import__("torch").cuda.is_available() else "cpu",
        choices=["cpu", "cuda"],
        description="Device used for inference. Defaults to 'cuda' if available, otherwise 'cpu'.",
    )
    index_file: Path = Field(
        default=None,  # type: ignore
        description="Path to save/load cached image embeddings. Should end with .npz. Defaults based on retriever_type.",
    )

    # SigLIP2-specific settings
    siglip2_model_id: str = Field(
        default="google/siglip2-base-patch16-224",
        description="Hugging Face model id used by SigLIP2 retrieval.",
    )

    # InternVideo2-specific settings
    internvideo2_model_id: str = Field(
        default="OpenGVLab/InternVideo2_CLIP_S",
        description="Hugging Face model id used by InternVideo2 retrieval.",
    )
    trust_remote_code: bool = Field(
        default=True,
        description="Whether to trust remote code when loading InternVideo2 from Hugging Face.",
    )

    def model_post_init(self, __context: object) -> None:
        """Set default index_file based on retriever_type if not provided."""
        if self.index_file is None:
            if self.retriever_type == "siglip2":
                self.index_file = Path("data") / Path("tmp") / "siglip2_image_index.npz"
            elif self.retriever_type == "internvideo2":
                self.index_file = Path("data") / Path("tmp") / "internvideo2_clip_s_image_index.npz"

    @property
    def model_id(self) -> str:
        """Get the model_id for the current retriever_type."""
        if self.retriever_type == "siglip2":
            return self.siglip2_model_id
        elif self.retriever_type == "internvideo2":
            return self.internvideo2_model_id
        raise ValueError(f"Unknown retriever_type: {self.retriever_type}")
