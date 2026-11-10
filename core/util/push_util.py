import json
import re

import requests
from datetime import datetime
import pytz


def get_beijing_time():
    """获取北京时间"""
    target_timezone = pytz.timezone('Asia/Shanghai')
    return datetime.now().astimezone(target_timezone)


def format_now():
    """格式化当前时间"""
    return get_beijing_time().strftime("%Y-%m-%d %H:%M:%S")


class PushConfig:
    """推送配置类"""

    def __init__(self,
                 push_plus_token=None,
                 push_plus_hour=None,
                 push_plus_max=30,
                 push_wechat_webhook_key=None,
                 telegram_bot_token=None,
                 telegram_chat_id=None,
                 server_chan_sendkey=None,
                 bark_key=None,
                 trigger=None):
        self.push_plus_token = push_plus_token
        self.push_plus_hour = push_plus_hour
        self.push_plus_max = int(push_plus_max) if push_plus_max else 30
        self.push_wechat_webhook_key = push_wechat_webhook_key
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.server_chan_sendkey = server_chan_sendkey
        self.bark_key = bark_key
        self.trigger = trigger


def push_plus(token, title, content, template="html"):
    """
    推送消息，默认 html 模板；传 template="txt" 可按纯文本原样展示（保留换行）
    :param token: PUSHPLUS 的token
    :param title: 推送标题
    :param content: 推送内容
    :param template: html / txt
    :return: none
    """
    requestUrl = f"http://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": title,
        "content": content,
        "template": template,
        "channel": "wechat"
    }
    try:
        response = requests.post(requestUrl, data=data, timeout=15)
        if response.status_code == 200:
            json_res = response.json()
            print(f"pushplus推送完毕：{json_res['code']}-{json_res['msg']}")
            return {"ok": True, "msg": f"{json_res.get('code')}-{json_res.get('msg')}"}
        print("pushplus推送失败")
        return {"ok": False, "msg": f"HTTP {response.status_code}"}
    except requests.exceptions.RequestException as e:
        print(f"pushplus推送网络异常: {e}")
        return {"ok": False, "msg": f"网络异常：{e}"}
    except Exception as e:
        print(f"pushplus推送未知异常: {e}")
        return {"ok": False, "msg": f"异常：{e}"}


def push_wechat_webhook(key, title, content):
    """
    推送企业微信通知，WebHook方式，需要注册企业微信并配置机器人到对应的推送群。然后提取对应的key

    使用 text 类型发送，保证多行文本原样展示（markdown 会把单换行合并成一行）

    :param key: WebHook机器人的key
    :param title: 推送标题
    :param content: 推送内容（纯文本，保留换行）
    :return:
    """

    requestUrl = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"

    payload = {
        "msgtype": "text",
        "text": {
            "content": f"{title}\n{content}"
        }
    }

    try:
        response = requests.post(requestUrl, json=payload, timeout=15)
        if response.status_code == 200:
            json_res = response.json()
            if json_res.get('errcode') == 0:
                print(f"企业微信推送完毕：{json_res['errmsg']}")
                return {"ok": True, "msg": str(json_res.get('errmsg', 'ok'))}
            msg = json_res.get('errmsg', '未知错误')
            print(f"企业微信推送失败：{msg}")
            return {"ok": False, "msg": f"HTTP 200，errcode={json_res.get('errcode')}：{msg}"}
        print("企业微信推送失败")
        return {"ok": False, "msg": f"HTTP {response.status_code}"}
    except requests.exceptions.RequestException as e:
        print(f"企业微信推送异常: {e}")
        return {"ok": False, "msg": f"网络异常：{e}"}
    except Exception as e:
        print(f"企业微信推送发生未知异常: {e}")
        return {"ok": False, "msg": f"异常：{e}"}


def push_serverchan(send_key, title, content):
    """
    推送 Server酱（https://sct.ftqq.com/），推送到微信服务号
    :param send_key: SCT 开头的 SendKey（微信扫码登录后复制）
    :param title: 推送标题
    :param content: 推送内容（markdown）
    :return: none
    """
    requestUrl = f"https://sctapi.ftqq.com/{send_key}.send"
    data = {"title": title, "desp": content}
    try:
        response = requests.post(requestUrl, data=data, timeout=15)
        if response.status_code == 200:
            json_res = response.json()
            if json_res.get('code') == 0:
                print("Server酱推送完毕")
                return {"ok": True, "msg": "ok"}
            msg = json_res.get('message', json_res)
            print(f"Server酱推送失败：{msg}")
            return {"ok": False, "msg": f"code={json_res.get('code')}：{msg}"}
        print(f"Server酱推送失败：HTTP {response.status_code}")
        return {"ok": False, "msg": f"HTTP {response.status_code}"}
    except requests.exceptions.RequestException as e:
        print(f"Server酱推送网络异常: {e}")
        return {"ok": False, "msg": f"网络异常：{e}"}
    except Exception as e:
        print(f"Server酱推送未知异常: {e}")
        return {"ok": False, "msg": f"异常：{e}"}


def push_bark(key_or_url, title, content):
    """
    推送 Bark（iPhone APP）
    :param key_or_url: Bark APP 里复制的 Key，或自建服务的完整 URL（如 https://bark.example.com/abcd）
    :param title: 推送标题
    :param content: 推送内容（纯文本）
    :return: none
    """
    value = (key_or_url or '').strip()
    if value.lower().startswith(('http://', 'https://')):
        requestUrl = value.rstrip('/')
    else:
        requestUrl = f"https://api.day.app/{value}"
    try:
        response = requests.post(requestUrl, json={"title": title, "body": content}, timeout=15)
        if response.status_code == 200:
            json_res = response.json()
            if json_res.get('code') == 200:
                print("Bark推送完毕")
                return {"ok": True, "msg": "ok"}
            msg = json_res.get('message', json_res)
            print(f"Bark推送失败：{msg}")
            return {"ok": False, "msg": f"code={json_res.get('code')}：{msg}"}
        print(f"Bark推送失败：HTTP {response.status_code}")
        return {"ok": False, "msg": f"HTTP {response.status_code}"}
    except requests.exceptions.RequestException as e:
        print(f"Bark推送网络异常: {e}")
        return {"ok": False, "msg": f"网络异常：{e}"}
    except Exception as e:
        print(f"Bark推送未知异常: {e}")
        return {"ok": False, "msg": f"异常：{e}"}


def buildWeChatContent(title, content) -> str:
    return f"""# {title}\n{content}"""


def push_telegram_bot(bot_token, chat_id, content):
    """
    推送消息类型为html 需要在外部组装html content
    :param bot_token: telegram bot token
    :param chat_id: telegram bot chat_id
    :param content: 推送内容
    :return: none
    """
    requestUrl = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id": int(chat_id),
        "text": content,
        "parse_mode": "HTML"
    }
    print(f"post to url: {requestUrl}")
    print(f"payload: {json.dumps(payload)}")
    try:
        response = requests.post(requestUrl, json=payload, timeout=15)
        if response.status_code == 200:
            json_res = response.json()
            if json_res.get('ok') is True:
                print(f"telegram bot推送完毕：{json_res['result']['message_id']}")
                return {"ok": True, "msg": "ok"}
            print(f"telegram bot推送失败: {json.dumps(json_res)}")
            return {"ok": False, "msg": f"HTTP 200，{json_res.get('description', json.dumps(json_res))}"}
        print(f"telegram bot推送失败: {response.status_code}")
        return {"ok": False, "msg": f"HTTP {response.status_code}"}
    except requests.exceptions.RequestException as e:
        print(f"telegram bot推送异常: {e}")
        return {"ok": False, "msg": f"网络异常：{e}"}
    except Exception as e:
        print(f"telegram bot推送发生未知异常: {e}")
        return {"ok": False, "msg": f"异常：{e}"}


def push_results(exec_results, summary, config: PushConfig):
    """推送所有结果"""
    if not_in_push_time_range(config):
        return
    push_to_push_plus(exec_results, summary, config)
    push_to_wechat_webhook(exec_results, summary, config)
    push_to_telegram_bot(exec_results, summary, config)
    push_to_serverchan(exec_results, summary, config)
    push_to_bark(exec_results, summary, config)


def push_test(config: PushConfig):
    """向每个已配置的渠道发送一条测试消息，返回各渠道结果。

    返回 [{"channel": "PushPlus", "ok": True/False/None, "msg": "..."}]
    ok 为 None 表示该渠道未配置（已跳过）；测试不受「推送整点」限制。
    """
    results = []
    title = f"{format_now()} 推送测试"
    body = "这是一条来自 mimotion-web 的测试推送，收到即表示该渠道配置可用。"

    def add(channel, ret):
        results.append({"channel": channel,
                        "ok": ret.get("ok"), "msg": ret.get("msg", "")})

    token = (config.push_plus_token or "").strip()
    if token and token != "NO":
        add("PushPlus", push_plus(token, title, f"<div>{body}</div>"))
    else:
        results.append({"channel": "PushPlus", "ok": None, "msg": "未配置，已跳过"})

    key = (config.push_wechat_webhook_key or "").strip()
    if key and key != "NO":
        add("企业微信", push_wechat_webhook(key, title, body))
    else:
        results.append({"channel": "企业微信", "ok": None, "msg": "未配置，已跳过"})

    sendkey = (config.server_chan_sendkey or "").strip()
    if sendkey:
        add("Server酱", push_serverchan(sendkey, title, body))
    else:
        results.append({"channel": "Server酱", "ok": None, "msg": "未配置，已跳过"})

    bark = (config.bark_key or "").strip()
    if bark:
        add("Bark", push_bark(bark, title, body))
    else:
        results.append({"channel": "Bark", "ok": None, "msg": "未配置，已跳过"})

    tg_token = (config.telegram_bot_token or "").strip()
    tg_chat = (config.telegram_chat_id or "").strip()
    if tg_token and tg_chat and tg_token != "NO":
        try:
            add("Telegram", push_telegram_bot(tg_token, tg_chat, f"<b>{body}</b>"))
        except Exception as e:
            add("Telegram", {"ok": False, "msg": f"Chat ID 非法：{e}"})
    else:
        results.append({"channel": "Telegram", "ok": None, "msg": "未配置，已跳过"})

    return results


def _display_name(user) -> str:
    """「脱敏账号（备注）」→ 展示名：优先备注，没填备注就用脱敏账号"""
    u = (user or '').strip()
    if u.endswith('）') and '（' in u:
        remark = u.rsplit('（', 1)[1][:-1].strip()
        if remark:
            return remark
    return u


def _parse_step(msg):
    """从 '修改步数（9697）[success]' 里取出步数"""
    m = re.search(r'修改步数（(\d+)）', msg or '')
    return m.group(1) if m else None


def _escape_html(text) -> str:
    return (str(text or '').replace('&', '&amp;')
            .replace('<', '&lt;').replace('>', '&gt;'))


def build_push_payload(exec_results, summary, config: PushConfig):
    """组装推送内容（树形明细版）

    标题：刷步数通知（✅ 3 / ❌ 0）
    正文：
    触发: 定时任务 11:43

    账号明细: 共 3 个
    ├ ✅ 备注名: 9697 步
    └ ❌ 备注名: 登陆失败！

    :return: (title, body)
    """
    total = len(exec_results)
    ok = sum(1 for r in exec_results if r.get('success') is True)
    fail = total - ok
    title = f"刷步数通知（✅ {ok} / ❌ {fail}）"

    trigger = getattr(config, 'trigger', None) or '手动执行'
    hhmm = get_beijing_time().strftime('%H:%M')
    lines = [f"触发: {trigger} {hhmm}", "", f"账号明细: 共 {total} 个"]

    if total == 0:
        lines.append("└ 没有执行任何账号")
    elif total >= config.push_plus_max:
        lines.append(f"└ 账号较多（{total} 个），明细请查看执行日志")
    else:
        for idx, r in enumerate(exec_results):
            branch = '└' if idx == total - 1 else '├'
            name = _display_name(r.get('user'))
            if r.get('success') is True:
                step = _parse_step(r.get('msg'))
                detail = f"{step} 步" if step else f"{r.get('msg')}"
                lines.append(f"{branch} ✅ {name}: {detail}")
            else:
                lines.append(f"{branch} ❌ {name}: {r.get('msg')}")

    return title, '\n'.join(lines)


def push_to_serverchan(exec_results, summary, config: PushConfig):
    """推送到Server酱"""
    if config.server_chan_sendkey and config.server_chan_sendkey.strip():
        title, body = build_push_payload(exec_results, summary, config)
        # Server酱按 markdown 渲染，用代码块保证换行与对齐不被合并
        ret = push_serverchan(config.server_chan_sendkey.strip(), title,
                              f"```\n{body}\n```")
        print(f"[推送] Server酱：{'成功' if ret['ok'] else '失败，' + ret['msg']}")
    else:
        print("[推送] Server酱：未配置，跳过")


def push_to_bark(exec_results, summary, config: PushConfig):
    """推送到Bark"""
    if config.bark_key and config.bark_key.strip():
        title, body = build_push_payload(exec_results, summary, config)
        ret = push_bark(config.bark_key.strip(), title, body)
        print(f"[推送] Bark：{'成功' if ret['ok'] else '失败，' + ret['msg']}")
    else:
        print("[推送] Bark：未配置，跳过")


def not_in_push_time_range(config: PushConfig) -> bool:
    """检查是否在推送时间范围内"""
    if not config.push_plus_hour:
        return False  # 如果没有设置推送时间，则总是推送

    time_bj = get_beijing_time()

    # 首先根据时间判断，如果匹配 直接返回
    if config.push_plus_hour.isdigit():
        if time_bj.hour == int(config.push_plus_hour):
            print(f"当前设置推送整点为：{config.push_plus_hour}, 当前整点为：{time_bj.hour}，执行推送")
            return False

    # 如果时间不匹配，检查cron_change_time文件中的记录
    # 读取cron_change_time文件中的最后一行数据：“next exec time: UTC(7:35) 北京时间(15:35)” 中的整点数
    # 然后用来对比是否当前时间，避免因为Actions执行延迟导致推送失效
    try:
        with open('cron_change_time', 'r') as f:
            lines = f.readlines()
            if lines:
                last_line = lines[-1].strip()
                # 提取北京时间的小时数
                import re
                match = re.search(r'北京时间\(0?(\d+):\d+\)', last_line)
                if match:
                    cron_hour = int(match.group(1))
                    if int(config.push_plus_hour) == cron_hour:
                        print(
                            f"当前设置推送整点为：{config.push_plus_hour}, 根据执行记录，本次执行整点为：{cron_hour}，执行推送")
                        return False
    except Exception as e:
        print(f"读取cron_change_time文件出错: {e}")
    print(f"当前整点时间为：{time_bj}，不在配置的推送时间，不执行推送")
    return True


def push_to_push_plus(exec_results, summary, config: PushConfig):
    """推送到PushPlus"""
    if config.push_plus_token and config.push_plus_token != '' and config.push_plus_token != 'NO':
        title, body = build_push_payload(exec_results, summary, config)
        # txt 模板才会原样保留换行，html 模板会把纯文本挤成一段
        ret = push_plus(config.push_plus_token, title, body, template="txt")
        print(f"[推送] PushPlus：{'成功' if ret['ok'] else '失败，' + ret['msg']}")
    else:
        print("[推送] PushPlus：未配置，跳过")


def push_to_wechat_webhook(exec_results, summary, config: PushConfig):
    """推送到企业微信"""
    # 判断是否需要微信推送
    if config.push_wechat_webhook_key and config.push_wechat_webhook_key != '' and config.push_wechat_webhook_key != 'NO':
        title, body = build_push_payload(exec_results, summary, config)
        ret = push_wechat_webhook(config.push_wechat_webhook_key, title, body)
        print(f"[推送] 企业微信：{'成功' if ret['ok'] else '失败，' + ret['msg']}")
    else:
        print("[推送] 企业微信：未配置，跳过")


def push_to_telegram_bot(exec_results, summary, config: PushConfig):
    """推送到Telegram"""
    # 判断是否需要telegram推送
    if (config.telegram_bot_token and config.telegram_bot_token != '' and config.telegram_bot_token != 'NO' and
            config.telegram_chat_id and config.telegram_chat_id != ''):
        title, body = build_push_payload(exec_results, summary, config)
        html = f"<b>{_escape_html(title)}</b>\n<pre>{_escape_html(body)}</pre>"
        ret = push_telegram_bot(config.telegram_bot_token, config.telegram_chat_id, html)
        print(f"[推送] Telegram：{'成功' if ret['ok'] else '失败，' + ret['msg']}")
    else:
        print("[推送] Telegram：未配置，跳过")
