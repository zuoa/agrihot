"""Editable collection definitions: public GET endpoints and declarative selectors."""
import ipaddress
import re
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lxml import etree
from pydantic import BaseModel, Field, field_validator, model_validator


class ListParserIn(BaseModel):
    model_config = {"extra": "forbid"}
    items: str = Field(default="", max_length=500)
    title: str = Field(default="", max_length=500)
    url: str = Field(default="", max_length=500)
    url_template: str = Field(default="", max_length=2000)
    published_at: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=500)
    content: str = Field(default="", max_length=500)
    doi: str = Field(default="", max_length=500)
    next_page: str = Field(default="", max_length=500)
    date_format: str = Field(default="", max_length=100)
    page_parameter: str = Field(default="", max_length=80, pattern=r"^[\w.-]*$")
    page_start: int = Field(default=1, ge=0, le=10000)
    page_size: int = Field(default=0, ge=0, le=500)


class SourceDefinitionIn(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["rss", "json", "html", "moa", "candidate"]
    url: str = Field(min_length=1, max_length=2000)
    enabled: bool = Field(default=False, strict=True)
    hosts: list[str] = Field(default_factory=list, max_length=30)
    article_pattern: str = Field(default=r"^/.*$", max_length=500)
    interval_minutes: int = Field(default=240, ge=1, le=10080)
    note: str = Field(default="", max_length=2000)
    keywords: list[str] = Field(default_factory=list, max_length=200)
    category: Literal["报道", "政策", "行业", "论文"] = "报道"
    default_timezone: str = Field(default="UTC", max_length=100)
    parser: ListParserIn = Field(default_factory=ListParserIn)

    @field_validator("url")
    @classmethod
    def public_url(cls, value):
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("请填写不含账户信息的 HTTP/HTTPS 公开地址")
        if parts.port not in (None, 80, 443):
            raise ValueError("采集地址仅支持标准 HTTP/HTTPS 端口")
        cls.check_host(parts.hostname)
        return value

    @staticmethod
    def check_host(host):
        if host.lower() == "localhost" or host.lower().endswith((".local", ".localhost")):
            raise ValueError("信源必须使用公开互联网地址")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r"[a-zA-Z0-9.-]+", host):
                raise ValueError("域名格式无效，请只填写主机名")
        else:
            if not address.is_global or address.is_multicast:
                raise ValueError("信源必须使用公开互联网地址")

    @model_validator(mode="after")
    def validate_rules(self):
        self.article_pattern = self.article_pattern or r"^/.*$"
        try:
            re.compile(self.article_pattern)
        except re.error as exc:
            raise ValueError(f"文章路径正则无效：{exc}") from None
        try:
            ZoneInfo(self.default_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("时区无效，例如 Asia/Shanghai 或 UTC") from None
        self.hosts = list(dict.fromkeys([urlsplit(self.url).hostname, *(h.strip().lower() for h in self.hosts)]))
        for host in self.hosts:
            self.check_host(host)
        if self.kind in {"json", "html"}:
            for key in ("items", "title", "url", "published_at"):
                if not getattr(self.parser, key).strip():
                    raise ValueError(f"列表解析必须填写 {key} 路径")
            for key in ("items", "title", "url", "published_at", "summary", "content", "doi", "next_page"):
                expression = getattr(self.parser, key).strip()
                setattr(self.parser, key, expression)
                if not expression:
                    continue
                try:
                    if self.kind == "json":
                        from jsonpath_ng.ext import parse
                        parse(expression)
                    else:
                        etree.XPath(expression)
                except Exception:
                    raise ValueError(f"{key} 的 {'JSONPath' if self.kind == 'json' else 'XPath'} 表达式无效") from None
            if self.category == "论文" and not self.parser.doi:
                raise ValueError("论文列表必须配置 DOI 路径")
            if self.parser.url_template and ("{value}" not in self.parser.url_template
                                            or "{value}" in urlsplit(self.parser.url_template).netloc):
                raise ValueError("链接模板须在路径或查询参数中包含 {value}，不能用于域名")
            if self.parser.next_page and self.parser.page_parameter:
                raise ValueError("下一页链接与页码参数请选择一种分页方式")
        return self
