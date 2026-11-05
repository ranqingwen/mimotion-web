# -*- coding: utf8 -*-
"""封装 mimotion 核心逻辑，供 Web 后台调用。

复用 core/main.py 中的 MiMotionRunner / run_single_account，
进程内保留 token 缓存，避免频繁登录触发 429。
"""
import os
import sys
import io
import json
import threading
import contextlib
import traceback
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(BASE_DIR, "core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

_run_lock = threading.Lock()

# 把 token 缓存文件固定到 data 目录（main.py 里用的是相对路径）
os.chdir(os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data")))


def _int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _setup_token_cache(m, cfg: dict):
    """初始化 main 模块的 AES token 缓存（run_once 与 query_steps 共用）。"""
    aes_key = (cfg.get("AES_KEY") or os.environ.get("AES_KEY") or "").strip()
    m.time_bj = m.get_beijing_time()
    m.encrypt_support = False
    m.user_tokens = getattr(m, "user_tokens", dict())
    if aes_key.encode("utf-8") and len(aes_key.encode("utf-8")) == 16:
        m.aes_key = aes_key.encode("utf-8")
        m.encrypt_support = True
        if not m.user_tokens:
            m.user_tokens = m.prepare_user_tokens()
    else:
        m.user_tokens = dict()
        print("AES_KEY 未设置或无效，本次将直接登录（不缓存 token）")


def _remark_names(cfg: dict, m) -> dict:
    """账号脱敏名 -> 带备注的展示名，如 ran****@gmail.com -> ran****@gmail.com（老婆）"""
    users = (cfg.get("USER") or "").split("#")
    remarks = (cfg.get("REMARKS") or "").split("#")
    mapping = {}
    for i, u in enumerate(users):
        masked = m.desensitize_user_name(u.strip())
        r = remarks[i].strip() if i < len(remarks) else ""
        if r:
            mapping[masked] = f"{masked}（{r}）"
    return mapping


def run_once(cfg: dict, trigger: str = "manual") -> dict:
    """执行一次刷步。cfg 为页面表单保存的配置字典。返回日志与结果摘要。"""
    with _run_lock:
        import main as m  # noqa: import core main.py (defs only)
        from util import push_util

        log_buf = io.StringIO()
        started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        success, summary = False, ""
        try:
            with contextlib.redirect_stdout(log_buf):
                # ---- AES token 持久化支持 ----
                _setup_token_cache(m, cfg)

                # ---- 配置 ----
                config = {
                    "USER": cfg.get("USER", ""),
                    "PWD": cfg.get("PWD", ""),
                    "MIN_STEP": str(_int(cfg.get("MIN_STEP"), 18000)),
                    "MAX_STEP": str(_int(cfg.get("MAX_STEP"), 25000)),
                    "SLEEP_GAP": str(_int(cfg.get("SLEEP_GAP"), 5)),
                    "USE_CONCURRENT": cfg.get("USE_CONCURRENT", "False"),
                    "PUSH_PLUS_TOKEN": cfg.get("PUSH_PLUS_TOKEN", ""),
                    "PUSH_PLUS_HOUR": cfg.get("PUSH_PLUS_HOUR", ""),
                    "PUSH_WECHAT_WEBHOOK_KEY": cfg.get("PUSH_WECHAT_WEBHOOK_KEY", ""),
                    "TELEGRAM_BOT_TOKEN": cfg.get("TELEGRAM_BOT_TOKEN", ""),
                    "TELEGRAM_CHAT_ID": cfg.get("TELEGRAM_CHAT_ID", ""),
                }
                m.config = config
                m.push_config = push_util.PushConfig(
                    push_plus_token=config.get("PUSH_PLUS_TOKEN"),
                    push_plus_hour=config.get("PUSH_PLUS_HOUR"),
                    push_plus_max=_int(config.get("PUSH_PLUS_MAX"), 30),
                    push_wechat_webhook_key=config.get("PUSH_WECHAT_WEBHOOK_KEY"),
                    telegram_bot_token=config.get("TELEGRAM_BOT_TOKEN"),
                    telegram_chat_id=config.get("TELEGRAM_CHAT_ID"),
                )
                m.sleep_seconds = float(_int(config.get("SLEEP_GAP"), 5))
                m.users = config.get("USER", "")
                m.passwords = config.get("PWD", "")
                if cfg.get("STEP_MODE") == "fixed":
                    # 固定步数模式：直接使用填写的值，忽略范围与时间缩放
                    fixed = _int(cfg.get("FIXED_STEP"), 0)
                    if fixed <= 0:
                        summary = "固定步数未填写或非法，跳过执行"
                        print(summary)
                        log_text = log_buf.getvalue() + f"\n[{trigger}] {summary}"
                        return {"time": started, "trigger": trigger,
                                "success": False, "summary": summary, "log": log_text}
                    m.min_step = m.max_step = fixed
                elif cfg.get("SCALE_BY_TIME", "True") == "True":
                    # 随时间线性递增：填写的范围为北京时间 22:00 时的设定范围，
                    # 更早执行按当前时间占比缩放（与上游 mimotion 项目说明一致）
                    m.min_step, m.max_step = m.get_min_max_by_time()
                else:
                    # 直接使用页面填写的范围
                    m.min_step = _int(cfg.get("MIN_STEP"), 18000)
                    m.max_step = _int(cfg.get("MAX_STEP"), 25000)
                m.use_concurrent = config.get("USE_CONCURRENT") == "True"

                if not m.users.strip() or not m.passwords.strip():
                    summary = "账号或密码未填写，跳过执行"
                else:
                    user_list = m.users.split("#")
                    passwd_list = m.passwords.split("#")
                    results = []
                    if len(user_list) != len(passwd_list):
                        summary = f"账号数[{len(user_list)}]和密码数[{len(passwd_list)}]不匹配，跳过执行"
                    else:
                        idx, total = 0, len(user_list)
                        if m.use_concurrent:
                            import concurrent.futures
                            with concurrent.futures.ThreadPoolExecutor() as ex:
                                results = list(ex.map(
                                    lambda x: m.run_single_account(total, x[0], *x[1]),
                                    enumerate(zip(user_list, passwd_list))))
                        else:
                            for user_mi, passwd_mi in zip(user_list, passwd_list):
                                results.append(m.run_single_account(total, idx, user_mi, passwd_mi))
                                idx += 1
                                if idx < total:
                                    import time as _t
                                    _t.sleep(m.sleep_seconds)
                        if m.encrypt_support:
                            m.persist_user_tokens()
                        ok_count = sum(1 for r in results if r["success"])
                        summary = f"执行账号总数{total}，成功：{ok_count}，失败：{total - ok_count}"
                        success = ok_count == total and total > 0
                        try:
                            push_util.push_results(results, summary, m.push_config)
                        except Exception:
                            print("推送异常：", traceback.format_exc())
        except Exception:
            summary = "执行异常：" + traceback.format_exc().splitlines()[-1]
            print(traceback.format_exc())

        print(f"[触发方式: {trigger}] {summary}")
        log_text = log_buf.getvalue() + f"\n[{trigger}] {summary}"
        # 日志中的脱敏账号追加备注，便于区分多个账号
        for masked, shown in _remark_names(cfg, m).items():
            log_text = log_text.replace(masked, shown)
        return {"time": started, "trigger": trigger, "success": success,
                "summary": summary, "log": log_text}


def query_steps(cfg: dict) -> dict:
    """查询各账号今日步数（只读操作，不修改步数）。
    返回 {"ok": True, "results": [{"user", "steps", "error"}], "log": str}
    """
    with _run_lock:
        import main as m

        log_buf = io.StringIO()
        results = []
        try:
            with contextlib.redirect_stdout(log_buf):
                _setup_token_cache(m, cfg)
                users = (cfg.get("USER") or "").strip()
                passwords = (cfg.get("PWD") or "").strip()
                if not users or not passwords:
                    return {"ok": False, "error": "请先填写账号和密码", "results": [], "log": ""}
                user_list = users.split("#")
                passwd_list = passwords.split("#")
                if len(user_list) != len(passwd_list):
                    return {"ok": False,
                            "error": f"账号数[{len(user_list)}]和密码数[{len(passwd_list)}]不匹配",
                            "results": [], "log": ""}
                gap = float(_int(cfg.get("SLEEP_GAP"), 5))
                remark_map = _remark_names(cfg, m)
                for idx, (user_mi, passwd_mi) in enumerate(zip(user_list, passwd_list)):
                    if idx:
                        import time as _t
                        _t.sleep(gap)
                    runner = m.MiMotionRunner(user_mi, passwd_mi)
                    steps, err, ok = runner.login_and_query_step()
                    print(f"[{idx + 1}/{len(user_list)}] {runner.log_str}")
                    masked = m.desensitize_user_name(user_mi)
                    results.append({
                        "user": remark_map.get(masked, masked),
                        "steps": steps,
                        "error": err,
                        "success": ok,
                    })
                if m.encrypt_support:
                    m.persist_user_tokens()
        except Exception:
            print(traceback.format_exc())
            return {"ok": False, "error": "查询异常：" + traceback.format_exc().splitlines()[-1],
                    "results": results, "log": log_buf.getvalue()}
        return {"ok": True, "results": results, "log": log_buf.getvalue()}
