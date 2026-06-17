# -*- coding: utf-8 -*-
"""The agent used to synthesize a long trajectory."""
from agentscope.tool import Toolkit
from agentscope.model import ChatModelBase
from agentscope.formatter import FormatterBase
from agentscope.memory import (
    MemoryBase, 
    LongTermMemoryBase,
) 
from agentscope.rag import KnowledgeBase
from agentscope.message import Msg
from agentscope.agent import ReActAgent
from agentscope.tool import ToolResponse 
from ._base import NotebookBase
from typing import Literal, Any 


class SynthesisAgent(ReActAgent): 
    """A trajectory synthesis agent based on `ReActAgent`."""

    def __init__(
        self, 
        name: str,
        sys_prompt: str,
        model: ChatModelBase,
        formatter: FormatterBase,
        toolkit: Toolkit | None = None,
        memory: MemoryBase | None = None,
        long_term_memory: LongTermMemoryBase | None = None,
        long_term_memory_mode: Literal[
            "agent_control",
            "static_control",
            "both",
        ] = "both",
        enable_meta_tool: bool = False, 
        parallel_tool_calls: bool = False,
        knowledge: KnowledgeBase | list[KnowledgeBase] | None = None,
        enable_rewrite_query: bool = True,
        notebook: NotebookBase | None = None,
        print_hint_msg: bool = False,
        max_iters: int = 10,
    ) -> None: 
        """Initialize a synthesis agent."""
        super().__init__(
            name,
            sys_prompt,
            model=model,
            formatter=formatter,
            toolkit=toolkit,
            memory=memory,
            long_term_memory=long_term_memory,
            long_term_memory_mode=long_term_memory_mode,
            enable_meta_tool=enable_meta_tool, 
            parallel_tool_calls=parallel_tool_calls,
            knowledge=knowledge,
            enable_rewrite_query=enable_rewrite_query,
            print_hint_msg=print_hint_msg,
            max_iters=max_iters,
        )

        self.notebook = None 
        if notebook is not None:
            self.notebook = notebook 
            if enable_meta_tool:
                group_name = self.notebook.name
                self.toolkit.create_tool_group(
                    group_name,
                    description=self.notebook.description,
                )
            else:
                group_name = "basic"
            for tool in self.notebook.list_tools():
                self.toolkit.register_tool_function(
                    tool, 
                    group_name=group_name,
                )
            
    async def _reasoning(
        self,
    ) -> Msg:
        """Perform the reasoning process."""
        # The logic is similar to `PlanNotebook` from `agentscope.plan`. 
        if self.notebook:
            # Insert the reasoning hint from the notebook. 
            hint_msg = await self.notebook.get_current_hint()
            if self.print_hint_msg and hint_msg:
                await self.print(hint_msg)
            await self._reasoning_hint_msgs.add(hint_msg)
        
        return await super()._reasoning()

    def generate_response(
        self,
        response: str,
        **kwargs: Any,
    ) -> ToolResponse:
        """Generate a response. Note only the input argument `response` is
        visible to the others, you should include all the necessary
        information in the `response` argument.

        Args:
            response (`str`):
                Your response to the user.
        """
        if self.notebook:
            check_response = self.notebook.is_finished()
            if not check_response.metadata["success"]: 
                return check_response  
        return super().generate_response(response, **kwargs)