# -*- coding: utf8 -*-
"""mimotion 本地 Docker 版 - 带登录的 Web 管理界面"""
import os
import json
import time
import random
import secrets
import threading
from datetime import timedelta
from functools import wraps
from datetime import datetime

import pytz

from flask import (Flask, session, redirect, url_for, request,
                   render_template, flash, jsonify)
from apscheduler.schedulers.background import BackgroundScheduler

import runner

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
LOG_PATH = os.path.join(DATA_DIR, "runlog.json")

WEB_USER = os.environ.get("WEB_USER", "admin")
WEB_PASS = os.environ.get("WEB_PASS", "admin123")

DEFAULT_CONFIG = {
    "USER": "",
    "PWD": "",
    "REMARKS": "",
    "MIN_STEP": "18000",
    "MAX_STEP": "25000",
    "SCALE_BY_TIME": "True",
    "MONOTONIC_STEPS": "True",
    "STEP_MODE": "range",
    "FIXED_STEP": "",
    "SCHEDULE_ENABLED": "True",
    "SLEEP_GAP": "5",
    "USE_CONCURRENT": "False",
    "HOURS": "9,12,15,18,20,22",
    "AES_KEY": "",
    "PUSH_PLUS_TOKEN": "",
    "PUSH_PLUS_HOUR": "",
    "PUSH_WECHAT_WEBHOOK_KEY": "",
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
}

app = Flask(__name__)

# ---- 持久化 flask secret key ----
_keyfile = os.path.join(DATA_DIR, "secret.key")
if os.path.exists(_keyfile):
    with open(_keyfile) as f:
        app.secret_key = f.read().strip()
else:
    app.secret_key = secrets.token_hex(32)
    with open(_keyfile, "w") as f:
        f.write(app.secret_key)

# ---- 简单防爆破 ----
_failed = {"count": 0, "locked_until": 0.0}
_fail_lock = threading.Lock()


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def append_log(entry):
    logs = []
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    logs.insert(0, entry)
    logs = logs[:50]
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


def load_logs():
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


# ---------------- 登录 ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def csrf_token():
    token = session.get("csrf")
    if not token:
        token = secrets.token_hex(16)
        session["csrf"] = token
    return token


def check_csrf():
    token = request.form.get("csrf", "")
    if not token or token != session.get("csrf"):
        return False
    return True


@app.route("/login", methods=["GET", "POST"])
def login():
    import time
    if request.method == "POST":
        with _fail_lock:
            now = time.time()
            if now < _failed["locked_until"]:
                return render_template("login.html", error="尝试次数过多，请 2 分钟后再试"), 429
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            if username == WEB_USER and password == WEB_PASS:
                _failed["count"] = 0
                session.clear()
                session["user"] = username
                session["csrf"] = secrets.token_hex(16)
                return redirect(url_for("dashboard"))
            _failed["count"] += 1
            if _failed["count"] >= 5:
                _failed["locked_until"] = now + 120
                _failed["count"] = 0
        return render_template("login.html", error="用户名或密码错误"), 401
    return render_template("login.html", error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- 主面板 ----------------
@app.route("/")
@login_required
def dashboard():
    cfg = load_config()
    users = cfg["USER"].split("#") if cfg["USER"].strip() else [""]
    pwds = cfg["PWD"].split("#") if cfg["PWD"].strip() else [""]
    remarks = cfg.get("REMARKS", "").split("#") if cfg.get("REMARKS", "").strip() else [""]
    # 账号/密码数量对齐
    n = max(len(users), len(pwds))
    users += [""] * (n - len(users))
    pwds += [""] * (n - len(pwds))
    remarks += [""] * (n - len(remarks))
    accounts = [{"user": u, "pwd": p, "remark": r} for u, p, r in zip(users, pwds, remarks)]
    return render_template("dashboard.html", cfg=cfg, accounts=accounts, csrf=csrf_token())


@app.route("/save", methods=["POST"])
@login_required
def save():
    if not check_csrf():
        return jsonify({"ok": False, "error": "CSRF 校验失败"}), 400
    cfg = load_config()
    # 动态账号列表：每行一个账号+密码
    users = [u.strip() for u in request.form.getlist("account_user")]
    pwds = [p.strip() for p in request.form.getlist("account_pwd")]
    # 备注可选；# 是账号分隔符，备注里不允许出现
    remarks = [r.strip().replace("#", "；") for r in request.form.getlist("account_remark")]
    rows = [
        (u, p, remarks[i] if i < len(remarks) else "")
        for i, (u, p) in enumerate(zip(users, pwds)) if u or p
    ]
    errs = []
    if not rows:
        errs.append("至少填写一个账号")
    else:
        for i, (u, p, _r) in enumerate(rows, 1):
            if not u or not p:
                errs.append(f"第 {i} 个账号的用户名或密码未填完整")
    if errs:
        return jsonify({"ok": False, "error": "；".join(errs)}), 400
    cfg["USER"] = "#".join(u for u, _, _r in rows)
    cfg["PWD"] = "#".join(p for _, p, _r in rows)
    cfg["REMARKS"] = "#".join(r for _, _, r in rows)
    for k in ("MIN_STEP", "MAX_STEP", "HOURS", "SLEEP_GAP", "USE_CONCURRENT",
              "AES_KEY", "PUSH_PLUS_TOKEN", "PUSH_PLUS_HOUR",
              "PUSH_WECHAT_WEBHOOK_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        cfg[k] = request.form.get(k, DEFAULT_CONFIG[k]).strip()
    # 复选框：未勾选时表单不会提交该字段
    cfg["SCALE_BY_TIME"] = "True" if request.form.get("SCALE_BY_TIME") == "True" else "False"
    cfg["MONOTONIC_STEPS"] = "True" if request.form.get("MONOTONIC_STEPS") == "True" else "False"
    # 步数模式：range=范围随机 / fixed=固定步数（互斥）
    cfg["STEP_MODE"] = "fixed" if request.form.get("STEP_MODE") == "fixed" else "range"
    cfg["FIXED_STEP"] = request.form.get("FIXED_STEP", "").strip()
    # 定时开关（由切换按钮维护，表单里以隐藏字段携带当前值）
    cfg["SCHEDULE_ENABLED"] = "True" if request.form.get("SCHEDULE_ENABLED") == "True" else "False"
    if cfg["STEP_MODE"] == "fixed":
        try:
            if int(cfg["FIXED_STEP"]) <= 0:
                raise ValueError
        except ValueError:
            errs.append("固定步数必须为正整数")
    # 校验（保留前面累积的错误，不重置 errs）
    if cfg["STEP_MODE"] == "range":
        # 仅范围随机模式校验 MIN/MAX；固定步数模式下这两个值不生效
        try:
            if int(cfg["MIN_STEP"]) <= 0 or int(cfg["MAX_STEP"]) <= 0 or int(cfg["MIN_STEP"]) > int(cfg["MAX_STEP"]):
                errs.append("步数范围不合法（需为正数且最小步数 ≤ 最大步数）")
        except ValueError:
            errs.append("步数必须为整数")
    hours = [h.strip() for h in cfg["HOURS"].split(",") if h.strip()]
    if not hours:
        errs.append("每天执行时间不能为空")
    elif cfg["STEP_MODE"] == "fixed" and len(hours) > 1:
        errs.append("固定步数模式下每天执行时间只能填一个时间点（多个时间会反复覆盖步数）")
    else:
        try:
            if any(not (0 <= int(h) <= 23) for h in hours):
                raise ValueError
        except ValueError:
            errs.append("执行时间格式不正确，应为 0-23 的整数（北京时间），用英文逗号分隔")
    if cfg["AES_KEY"] and len(cfg["AES_KEY"].encode("utf-8")) != 16:
        errs.append("AES_KEY 长度必须恰好为 16 个字符（不要用中文）")
    if errs:
        return jsonify({"ok": False, "error": "；".join(errs)}), 400
    save_config(cfg)
    reschedule()
    return jsonify({"ok": True})


# 执行状态（供前端轮询；手动与定时任务共用，finished_ts 为完成事件标记）
_run_state = {"running": False, "done": False, "success": False, "summary": "",
              "trigger": "", "finished_ts": 0.0}


def _next_run_ts():
    """下次定时执行的 Unix 时间戳（供前端安排监视窗口）；未排程返回 None"""
    if load_config().get("SCHEDULE_ENABLED", "True") != "True":
        return None
    job = scheduler.get_job("mimotion")
    if job and job.next_run_time:
        return job.next_run_time.timestamp()
    return None


def _now_bj():
    return datetime.now(pytz.timezone("Asia/Shanghai"))


@app.route("/run", methods=["POST"])
@login_required
def run():
    if not check_csrf():
        return jsonify({"ok": False, "error": "CSRF 校验失败"}), 400
    cfg = load_config()
    if not cfg["USER"].strip() or not cfg["PWD"].strip():
        return jsonify({"ok": False, "error": "请先填写账号和密码"}), 400
    if _run_state["running"]:
        return jsonify({"ok": False, "error": "上一次执行还没结束，请稍候"}), 400
    _run_state.update({"running": True, "done": False, "success": False,
                       "summary": "", "trigger": "手动执行"})

    def _job():
        try:
            result = runner.run_once(cfg, trigger="手动执行")
            append_log(result)
            _run_state.update({"running": False, "done": True,
                               "success": result.get("success", False),
                               "summary": result.get("summary", ""),
                               "trigger": "手动执行",
                               "finished_ts": time.time()})
        except Exception as e:
            append_log({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "trigger": "手动执行", "success": False,
                        "summary": f"后台异常: {e}", "log": ""})
            _run_state.update({"running": False, "done": True, "success": False,
                               "summary": f"后台异常: {e}", "trigger": "手动执行",
                               "finished_ts": time.time()})
    threading.Thread(target=_job, daemon=True).start()
    return jsonify({"ok": True, "msg": "已开始执行，完成后自动更新状态并刷新日志"})


@app.route("/run-status")
@login_required
def run_status():
    return jsonify({**_run_state, "next_run_ts": _next_run_ts()})


@app.route("/query", methods=["POST"])
@login_required
def query():
    """查询各账号今日步数（同步返回，只读操作）"""
    if not check_csrf():
        return jsonify({"ok": False, "error": "CSRF 校验失败"}), 400
    cfg = load_config()
    if not cfg["USER"].strip() or not cfg["PWD"].strip():
        return jsonify({"ok": False, "error": "请先填写账号和密码"}), 400
    try:
        return jsonify(runner.query_steps(cfg))
    except Exception as e:
        return jsonify({"ok": False, "error": f"查询异常: {e}", "results": [], "log": ""}), 500


@app.route("/logs")
@login_required
def logs():
    return jsonify(load_logs()[:10])


@app.route("/toggle-schedule", methods=["POST"])
@login_required
def toggle_schedule():
    if not check_csrf():
        return jsonify({"ok": False, "error": "CSRF 校验失败"}), 400
    cfg = load_config()
    enabled = cfg.get("SCHEDULE_ENABLED", "True") == "True"
    cfg["SCHEDULE_ENABLED"] = "False" if enabled else "True"
    save_config(cfg)
    reschedule()
    return jsonify({"ok": True, "enabled": cfg["SCHEDULE_ENABLED"] == "True"})


@app.route("/reshuffle", methods=["POST"])
@login_required
def reshuffle():
    """重新随机执行分钟（不改变配置）"""
    if not check_csrf():
        return jsonify({"ok": False, "error": "CSRF 校验失败"}), 400
    reschedule()
    return jsonify({"ok": True, "next": next_run_time()})


# ---------------- 定时调度 ----------------
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def scheduled_run():
    cfg = load_config()
    try:
        result = runner.run_once(cfg, trigger="定时任务")
    except Exception as e:
        result = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  "trigger": "定时任务", "success": False,
                  "summary": f"后台异常: {e}", "log": ""}
    append_log(result)
    # 记录完成事件（前端监视到 finished_ts 变化后自动刷新日志）
    _run_state.update({"running": False, "done": True,
                       "success": result.get("success", False),
                       "summary": result.get("summary", ""),
                       "trigger": "定时任务",
                       "finished_ts": time.time()})
    # 执行完后安排下一个时间点（跳过刚执行的小时，避免同小时重复执行）
    reschedule(skip_hour=_now_bj().hour)


def reschedule(skip_hour=None):
    """排下一次定时执行。
    skip_hour：定时任务执行完后调用时传入刚执行的小时（北京时间），
    确保该小时不会因随机分钟落在其后而被再次排程（每个时间点每天只执行一次）。
    """
    cfg = load_config()
    # 定时被取消时不排程
    if cfg.get("SCHEDULE_ENABLED", "True") != "True":
        if scheduler.get_job("mimotion"):
            scheduler.remove_job("mimotion")
        return
    hours = []
    for h in cfg.get("HOURS", "").split(","):
        h = h.strip()
        if h and h.isdigit() and 0 <= int(h) <= 23:
            hours.append(int(h))
    if not hours:
        return
    now = _now_bj()
    run_at = None
    for h in sorted(set(hours)):
        if skip_hour is not None and h == skip_hour:
            continue  # 该时间点刚执行过，不再重复
        cand = now.replace(hour=h, minute=random.randint(0, 59),
                           second=0, microsecond=0)
        if cand > now:
            run_at = cand
            break
    if run_at is None:
        # 今天的时间点都已过（或刚执行完最后一个）：安排到明天最早的时间点
        first = min(h for h in hours if h != skip_hour) if len(set(hours)) > 1 else min(hours)
        run_at = (now + timedelta(days=1)).replace(
            hour=first, minute=random.randint(0, 59), second=0, microsecond=0)
    scheduler.add_job(scheduled_run, "date", run_date=run_at,
                      id="mimotion", replace_existing=True)


scheduler.start()
reschedule()


def next_run_time():
    cfg = load_config()
    if cfg.get("SCHEDULE_ENABLED", "True") != "True":
        return "已取消自动执行"
    job = scheduler.get_job("mimotion")
    if job and job.next_run_time:
        return job.next_run_time.strftime("%Y-%m-%d %H:%M")
    return "未排程（请保存有效的执行时间）"


@app.context_processor
def inject_next_run():
    return {"next_run_time": next_run_time()}


# waitress 兼容入口
server = app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
