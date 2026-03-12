"""Pydantic models for user-app interaction records."""
from __future__ import annotations
from pydantic import BaseModel, Field
from .session import Message
from ..utils import get_timestamp
from typing import ClassVar


class AppInteractionBase(BaseModel):
    """Base class for user-app interaction records."""

    _app_name: ClassVar[str] = "App" 

    timestamp: str = Field(default_factory=get_timestamp)

    def interpret(self) -> str:
        """Interpret this interaction record into a natural-language text."""
        return "The user interacts with an app."

    def to_message(self) -> Message:
        """Create a message object whose content is the interpreted text and metadata is this record."""
        msg = Message(
            name=self._app_name,
            role="system",
            timestamp=self.timestamp,
            content=self.interpret(),
            side_note="It is a system message that represents the user's interaction with an app.",
        )
        msg.update_metadata(self.model_dump(mode="python"))
        return msg


class VoiceMemoInteraction(AppInteractionBase):
    """Voice memo interaction record."""

    _app_name: ClassVar[str] = "Voice Memo"

    id: str | None = None
    user_id: str | None = None

    transcript: str
    duration_seconds: int
    scene: str | None = None
    scene_description: str | None = None
    has_noise: bool | None = None
    noise_type: str | None = None
    is_fragmented: bool | None = None
    has_filler_words: bool | None = None
    key_info: list[str] | None = None
    tags: list[str] | None = None

    def interpret(self) -> str:
        return f"用户录制了一条语音备忘（时长：{self.duration_seconds} 秒）：{self.transcript}"


class CalendarInteraction(AppInteractionBase):
    """Calendar event interaction record."""

    _app_name: ClassVar[str] = "Calendar"

    id: str | None = None
    user_id: str | None = None

    title: str = ""
    description: str
    start_time: str | None = None
    end_time: str | None = None
    is_all_day: bool | None = None
    location: str | None = None
    attendees: list[str] | None = None
    topic: str | None = None
    reminder_minutes: int | None = None
    tags: list[str] | None = None

    def interpret(self) -> str:
        title = self.title or "无标题日程"

        start_time = self.start_time or "未知"
        end_time = self.end_time or "未知"
        time_span = f"开始时间：{start_time}\n结束时间：{end_time}"

        reminder = "提醒：（无提醒设定）"
        if self.reminder_minutes is not None:
            reminder = f"提醒：提前 {self.reminder_minutes} 分钟"

        desc = "日程描述：（无描述）"
        if self.description is not None:
            desc = f"日程描述：{self.description}"

        return "\n".join(
            [
                f"用户在日历中记录了日程《{title}》",
                "相关设定如下：",
                time_span,
                reminder,
                desc,
            ],
        )


class NoteInteraction(AppInteractionBase):
    """Note interaction record."""

    _app_name: ClassVar[str] = "Note"

    title: str | None = None
    content: str = ""
    topic: str | None = None
    entities: list[str] | None = None

    def interpret(self) -> str:
        title = self.title or "无标题便签"
        content = self.content or "（无内容）"
        return "\n".join(
            [
                f"用户在便签中记录了《{title}》",
                f"内容：{content}",
            ],
        )


class TodoInteraction(AppInteractionBase):
    """Todo interaction record."""

    _app_name: ClassVar[str] = "Todo"

    id: str | None = None
    user_id: str | None = None
    created_at: str | None = None

    title: str = ""
    content: str | None = None
    description: str | None = None
    due_date: str | None = None
    priority: int | None = None
    is_completed: bool | None = None
    is_finished: bool | None = None
    topic: str | None = None
    tags: list[str] | None = None

    def interpret(self) -> str:
        title = self.title or "无标题待办"
        status = ""
        if self.is_completed is True or self.is_finished is True:
            status = "状态：已完成"
        elif self.is_completed is False or self.is_finished is False:
            status = "状态：未完成"

        due = f"截止：{self.due_date}" if self.due_date is not None else "截止：无截止日期"
        prio = f"优先级：{self.priority}" if self.priority is not None else "优先级：无优先级"
        detail = f"内容：{self.content}" if self.content is not None else "内容：无内容"
        
        if not status or status == "状态：未完成":
            return "\n".join(
                [
                    f"用户创建了一个待办《{title}》",
                    due,
                    prio,
                    status,
                    detail,
                ],
            )
        else:
            return "\n".join(
                [
                    f"用户完成了一个待办《{title}》",
                    due,
                    prio,
                    status,
                    detail,
                ],
            )


class ScreenInteraction(AppInteractionBase):
    """Screen interaction record."""

    _app_name: ClassVar[str] = "Screen Memo"

    id: str | None = None
    user_id: str | None = None

    content: str 

    def interpret(self) -> str:
        content = (self.content or "").strip()
        if not content:
            return f"用户在手机上看了以下内容：\n（未知内容）"
        return f"用户在手机上看了以下内容：\n{content}"


class BillInteraction(AppInteractionBase):
    """Bill interaction record."""

    _app_name: ClassVar[str] = "Bill"

    id: str | None = None
    user_id: str | None = None

    entities: list[str] | None = None
    tags: list[str] | None = None

    bill_id: str | None = None

    type: str | None = None
    transaction_type: str | None = None
    amount: float | None = None
    payment_source: str | None = None
    category: str | None = None
    merchant_name: str | None = None
    merchant_name_en: str | None = None
    product_name: str | None = None

    sys_record_id: str | None = None 

    currency: str | None = None
    primary_amount: float | None = None
    primary_currency: str | None = None

    def interpret(self) -> str:
        merchant = self.merchant_name or "未知商户"
        product = self.product_name or "未知商品/服务"

        amount_str = "金额未知"
        if self.amount is not None:
            currency = self.currency or self.primary_currency or "CNY"
            amount_str = f"{self.amount:.2f} {currency}"

        if self.category is None:
            cat = "类别：未知"
        elif self.category == "medical":
            cat = "类别：医疗"
        elif self.category == "transportation":
            cat = "类别：交通"
        elif self.category == "meals":
            cat = "类别：餐饮"
        elif self.category == "livingExpenses":
            cat = "类别：生活费"
        elif self.category == "shopping":
            cat = "类别：购物"
        elif self.category == "dailyNecessities":
            cat = "类别：日用品"
        elif self.category == "snacks":
            cat = "类别：零食"
        elif self.category == "clothing":
            cat = "类别：服装"
        elif self.category == "salary":
            cat = "类别：工资"
        elif self.category == "billsPayment":
            cat = "类别：水电费"
        elif self.category == "telecommunication":
            cat = "类别：通讯费"
        else: 
            cat = "类别：未知"
        
        if self.payment_source is None: 
            pay = "支付方式：未知" 
        elif self.payment_source == "cash":
            pay = "支付方式：现金"
        elif self.payment_source == "bank_card":
            pay = "支付方式：银行卡"
        elif self.payment_source == "alipay":
            pay = "支付方式：支付宝"
        elif self.payment_source == "wechat_pay":
            pay = "支付方式：微信支付"
        else:
            pay = "支付方式：未知"

        if self.transaction_type is None:
            ttype = "交易类型：未知"
        elif self.transaction_type == "expenses":
            ttype = "交易类型：支出"
        elif self.transaction_type == "income":
            ttype = "交易类型：收入"
        else:
            ttype = "交易类型：未知"

        return "\n".join(
            [
                f"用户和 {merchant} 之间产生了一笔账单记录。",
                f"商品：{product}",
                f"金额：{amount_str}",
                ttype,
                cat,
                pay,
            ],
        )


class DocumentInteraction(AppInteractionBase):
    """Document interaction record."""

    _app_name: ClassVar[str] = "Document"

    id: str | None = None
    user_id: str | None = None

    entities: list[str] | None = None
    tags: list[str] | None = None

    title: str | None = None
    content: str | None = None
    page_count: int | None = None
    topic: str | None = None
    format: str | None = None

    def interpret(self) -> str:
        title = self.title or "无标题文档"
        topic = self.topic or "无主题"
        fmt = self.format or "未知格式"

        pages = "页数：未知"
        if self.page_count is not None:
            pages = f"页数：{self.page_count}"

        content_preview = "内容：无内容"
        if self.content:
            content_preview = f"内容：\n{self.content}"

        return "\n".join(
            [
                f"用户保存了一份文档《{title}》。",
                f"主题：{topic}",
                f"格式：{fmt}",
                pages,
                content_preview,
            ],
        )

