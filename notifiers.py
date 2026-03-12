# -*- coding: utf-8 -*-
"""
告警通知：支持 Telegram 群组消息与 Lark（飞书）webhook 发送（Python 2.7）
"""
from __future__ import print_function
import json
import urllib2
import ssl


def _format_alert_message(alerts, title="Monitor Hosts 告警"):
    """将告警列表格式化为可读文本。"""
    lines = ["【{0}】共 {1} 条告警".format(title, len(alerts)), ""]
    for i, a in enumerate(alerts, 1):
        host = a.get("host", "")
        metric = a.get("metric", "")
        msg = a.get("message", "")
        part = "[%s] " % host if host else ""
        part += "[%s] " % metric if metric else ""
        part += msg
        lines.append("{0}. {1}".format(i, part))
    return "\n".join(lines)


def _send_telegram(bot_token, chat_id, text, logger=None):
    """
    通过 Telegram Bot API 发送群组消息。
    bot_token: 从 @BotFather 获取；chat_id: 群组 ID（可为负数）。
    """
    if not bot_token or not chat_id:
        if logger:
            logger.warning("Telegram: bot_token 或 chat_id 未配置，跳过发送")
        return False
    url = "https://api.telegram.org/bot{0}/sendMessage".format(bot_token.strip())
    payload = {"chat_id": chat_id.strip(), "text": text, "disable_web_page_preview": True}
    try:
        body = json.dumps(payload)
        if isinstance(body, unicode):
            body = body.encode("utf-8")
        req = urllib2.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        # Python 2.7 下 HTTPS 可能需忽略证书校验（按环境可选）
        try:
            resp = urllib2.urlopen(req, timeout=15)
        except urllib2.URLError as e:
            if hasattr(e, "reason") and "CERTIFICATE" in str(e.reason).upper():
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                resp = urllib2.urlopen(req, timeout=15, context=ctx)
            else:
                raise
        code = resp.getcode()
        body = resp.read()
        if code != 200:
            if logger:
                logger.warning("Telegram 发送失败: HTTP %s %s", code, body[:200])
            return False
        out = json.loads(body) if body else {}
        if not out.get("ok"):
            if logger:
                logger.warning("Telegram API 返回错误: %s", out)
            return False
        return True
    except Exception as e:
        if logger:
            logger.exception("Telegram 发送异常: %s", e)
        return False


def _send_lark(webhook_url, text, logger=None):
    """
    通过 Lark（飞书）群机器人 webhook 发送文本消息。
    webhook_url: 在群设置中添加自定义机器人后获得的 webhook 地址。
    """
    if not webhook_url or not webhook_url.strip():
        if logger:
            logger.warning("Lark: webhook_url 未配置，跳过发送")
        return False
    url = webhook_url.strip()
    payload = {"msg_type": "text", "content": {"text": text}}
    try:
        body = json.dumps(payload)
        if isinstance(body, unicode):
            body = body.encode("utf-8")
        req = urllib2.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib2.urlopen(req, timeout=15)
        except urllib2.URLError as e:
            if hasattr(e, "reason") and "CERTIFICATE" in str(e.reason).upper():
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                resp = urllib2.urlopen(req, timeout=15, context=ctx)
            else:
                raise
        code = resp.getcode()
        body = resp.read()
        if code != 200:
            if logger:
                logger.warning("Lark 发送失败: HTTP %s %s", code, body[:200])
            return False
        out = json.loads(body) if body else {}
        if out.get("code") not in (None, 0):
            if logger:
                logger.warning("Lark webhook 返回错误: %s", out)
            return False
        return True
    except Exception as e:
        if logger:
            logger.exception("Lark 发送异常: %s", e)
        return False


def send_alert_notifications(alerts, config, logger=None):
    """
    根据配置发送告警到 Telegram 和/或 Lark。
    alerts: 告警列表，每项为 dict，含 host/metric/message 等。
    config: 完整配置字典，从中读取 alerts_notify.telegram / alerts_notify.lark。
    logger: 可选，用于打日志。
    """
    if not alerts:
        return
    notify_cfg = config.get("alerts_notify") or {}
    if not notify_cfg.get("enabled"):
        return
    text = _format_alert_message(alerts)
    sent_any = False
    tg = notify_cfg.get("telegram") or {}
    if tg.get("enabled") and tg.get("bot_token") and tg.get("chat_id"):
        if _send_telegram(tg.get("bot_token"), tg.get("chat_id"), text, logger):
            sent_any = True
    lk = notify_cfg.get("lark") or {}
    if lk.get("enabled") and lk.get("webhook_url"):
        if _send_lark(lk.get("webhook_url"), text, logger):
            sent_any = True
    if logger and sent_any:
        logger.info("告警已发送至已启用的通知渠道")


# 测试消息正文（与真实告警区分）
_TEST_MESSAGE = u"【Monitor Hosts】这是一条测试消息。若收到说明告警通知配置正确。"


def send_test_message(channel, config, form_overrides=None, logger=None):
    """
    发送测试消息到指定渠道，用于验证配置是否正确。
    channel: "telegram" | "lark" | "all"
    config: 完整配置，从中读 alerts_notify（当 form_overrides 未提供时使用）
    form_overrides: 可选，dict，如 {"telegram": {"bot_token": "", "chat_id": ""}, "lark": {"webhook_url": ""}}，用于用当前表单值测试而不保存
    logger: 可选
    返回: {"ok": bool, "telegram": bool|None, "lark": bool|None, "error": str}
    """
    result = {"ok": False, "telegram": None, "lark": None, "error": ""}
    notify = config.get("alerts_notify") or {}
    over = form_overrides or {}
    text = _TEST_MESSAGE
    if isinstance(text, str) and hasattr(text, "decode"):
        try:
            text = text.decode("utf-8")
        except Exception:
            pass
    errors = []

    if channel in ("telegram", "all"):
        tg = over.get("telegram") or notify.get("telegram") or {}
        bot_token = (tg.get("bot_token") or "").strip()
        chat_id = (tg.get("chat_id") or "").strip()
        if bot_token and chat_id:
            result["telegram"] = _send_telegram(bot_token, chat_id, text, logger)
        else:
            result["telegram"] = False
            errors.append("Telegram: 请填写 Bot Token 与 Chat ID")
    if channel in ("lark", "all"):
        lk = over.get("lark") or notify.get("lark") or {}
        webhook_url = (lk.get("webhook_url") or "").strip()
        if webhook_url:
            result["lark"] = _send_lark(webhook_url, text, logger)
        else:
            result["lark"] = False
            errors.append("Lark: 请填写 Webhook URL")

    result["ok"] = (result.get("telegram") is True or result.get("lark") is True)
    if not result["ok"] and errors:
        result["error"] = "; ".join(errors)
    elif not result["ok"]:
        result["error"] = "未配置或发送失败"
    return result
