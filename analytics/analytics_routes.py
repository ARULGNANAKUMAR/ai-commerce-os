"""
analytics/analytics_routes.py  +  embed/embed_routes.py  +  admin/admin_routes.py
Combined Phase 5 blueprints — each registered with its own url_prefix.
"""

# ─────────────────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────────────────
from flask import Blueprint, g, request, Response

from security import jwt_required
from security_ext import rate_limit, admin_required, cors_preflight
from utils import ApiError, api_response
from config import Config
import models
from analytics.analytics_service import compute_analytics, get_audit_timeline

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")


def _mid() -> str:
    if g.merchant_id:
        return g.merchant_id
    m = models.find_merchant_by_user_id(g.user_id)
    if not m:
        raise ApiError("Merchant profile not found.", 403, code="NO_MERCHANT")
    return str(m["_id"])


@analytics_bp.route("", methods=["GET"])
@jwt_required
def get_analytics():
    return api_response(data=compute_analytics(_mid()))


@analytics_bp.route("/timeline", methods=["GET"])
@jwt_required
def get_timeline():
    limit = min(int(request.args.get("limit", 50)), 200)
    return api_response(data={"timeline": get_audit_timeline(_mid(), limit=limit)})


@analytics_bp.route("/history", methods=["GET"])
@jwt_required
def get_history():
    days = min(int(request.args.get("days", 30)), 90)
    rows = models.find_analytics(_mid(), days=days)
    return api_response(data={"history": [
        {k: v for k, v in r.items() if k not in ("_id", "merchant_id")}
        for r in rows
    ]})


# ─────────────────────────────────────────────────────────────────────
# Embed SDK
# ─────────────────────────────────────────────────────────────────────

embed_bp = Blueprint("embed", __name__, url_prefix="/api/embed")

_WIDGET_TYPES = {"chat", "compare", "buy"}

_EMBED_SNIPPET = """<!-- AI Commerce OS Embed SDK -->
<script>
(function(w,d,s,c){{
  w.ACOS=w.ACOS||{{}};
  w.ACOS.merchantId='{merchant_id}';
  w.ACOS.widget='{widget}';
  w.ACOS.baseUrl='{base_url}';
  var sc=d.createElement(s); sc.src=c; sc.async=true;
  d.head.appendChild(sc);
}})
(window,document,'script','{base_url}/static/embed-widget.js');
</script>"""

_WIDGET_INIT_JS = """;(function(){{
  if(!window.ACOS||!window.ACOS.merchantId)return;
  var cfg=window.ACOS;
  var container=document.createElement('div');
  container.id='acos-widget-root';
  container.style.cssText='position:fixed;bottom:24px;right:24px;z-index:9999;';
  var btn=document.createElement('button');
  btn.textContent='💬 Ask AI';
  btn.style.cssText='padding:12px 20px;border-radius:999px;border:none;'+
    'background:#3395FF;color:#fff;font-family:sans-serif;font-size:14px;'+
    'font-weight:600;cursor:pointer;box-shadow:0 4px 16px rgba(51,149,255,0.35);';
  btn.onclick=function(){{
    var f=document.getElementById('acos-frame');
    if(f){{f.style.display=f.style.display==='none'?'flex':'none';return;}}
    var frame=document.createElement('iframe');
    frame.id='acos-frame';
    frame.src=cfg.baseUrl+'/embed/chat?mid='+cfg.merchantId;
    frame.style.cssText='width:380px;height:560px;border:none;border-radius:16px;'+
      'box-shadow:0 8px 32px rgba(0,0,0,0.18);position:fixed;bottom:80px;right:24px;'+
      'z-index:9998;display:flex;background:#fff;';
    document.body.appendChild(frame);
  }};
  container.appendChild(btn);
  document.body.appendChild(container);
}})();"""


@embed_bp.route("/code", methods=["GET"])
@jwt_required
def get_embed_code():
    widget = request.args.get("widget", "chat")
    if widget not in _WIDGET_TYPES:
        raise ApiError(f"widget must be one of: {', '.join(_WIDGET_TYPES)}", 400,
                       code="INVALID_WIDGET")
    merchant_id = _mid()
    snippet = _EMBED_SNIPPET.format(
        merchant_id=merchant_id,
        widget=widget,
        base_url=Config.APP_BASE_URL,
    )
    return api_response(data={
        "snippet": snippet,
        "widget":  widget,
        "merchant_id": merchant_id,
        "instructions": [
            "Copy the snippet into your website's <head> or just before </body>.",
            "The AI chat button will appear in the bottom-right corner of your site.",
            "Customers can search, compare, and add to cart without leaving your page.",
        ],
    })


@embed_bp.route("/widgets", methods=["GET"])
@jwt_required
def list_widgets():
    merchant_id = _mid()
    return api_response(data={"widgets": [
        {
            "type": t,
            "label": {"chat": "AI Shopping Chat", "compare": "Product Comparison",
                      "buy": "Buy with AI"}[t],
            "embed_url": f"{Config.APP_BASE_URL}/embed/{t}?mid={merchant_id}",
            "snippet_url": f"{Config.APP_BASE_URL}/api/embed/code?widget={t}",
        }
        for t in _WIDGET_TYPES
    ]})


# Public embed widget JS served to merchant storefronts
@embed_bp.route("/widget.js", methods=["GET", "OPTIONS"])
@cors_preflight
def widget_js():
    """Serve the self-initialising embed widget script."""
    return Response(
        _WIDGET_INIT_JS,
        mimetype="application/javascript",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# Public chat iframe shell served inside the embed widget
@embed_bp.route("/chat", methods=["GET"])
def embed_chat_shell():
    mid = request.args.get("mid", "")
    html = f"""<!doctype html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Shopping Assistant</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}
body{{background:#fff;display:flex;flex-direction:column;height:100vh;font-size:14px}}
#msgs{{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}}
.msg{{max-width:80%;padding:10px 14px;border-radius:14px;line-height:1.45}}
.msg.user{{align-self:flex-end;background:#3395FF;color:#fff;border-bottom-right-radius:4px}}
.msg.bot{{align-self:flex-start;background:#F0F4FA;color:#16213E;border-bottom-left-radius:4px}}
#bar{{display:flex;gap:8px;padding:12px;border-top:1px solid #E3E8F0}}
#bar input{{flex:1;padding:10px 14px;border:1px solid #E3E8F0;border-radius:999px;outline:none;font-size:13px}}
#bar button{{padding:10px 16px;background:#3395FF;color:#fff;border:none;border-radius:999px;cursor:pointer;font-size:13px}}
.hdr{{padding:12px 16px;background:#0B1F3A;color:#fff;font-weight:700;font-size:13px;flex-shrink:0}}
</style></head>
<body>
<div class="hdr">🤖 AI Shopping Assistant</div>
<div id="msgs">
  <div class="msg bot">Hi! I'm your AI shopping assistant. What are you looking for?</div>
</div>
<div id="bar">
  <input id="inp" placeholder="Ask about products…" autocomplete="off">
  <button onclick="send()">Send</button>
</div>
<script>
var sid=null,mid='{mid}',base=window.location.origin;
document.getElementById('inp').addEventListener('keydown',function(e){{if(e.key==='Enter')send();}});
function addMsg(role,text){{
  var d=document.getElementById('msgs');
  var m=document.createElement('div');
  m.className='msg '+role;
  m.textContent=text;
  d.appendChild(m);
  d.scrollTop=d.scrollHeight;
}}
async function send(){{
  var inp=document.getElementById('inp');
  var msg=inp.value.trim();
  if(!msg)return;
  inp.value='';
  addMsg('user',msg);
  try{{
    var r=await fetch(base+'/api/embed/agent',{{
      method:'POST',
      headers:{{'Content-Type':'application/json','X-Merchant-Id':mid}},
      body:JSON.stringify({{message:msg,session_id:sid}})
    }});
    var j=await r.json();
    sid=j.data&&j.data.session_id||sid;
    addMsg('bot',j.data&&j.data.reply||'Sorry, something went wrong.');
  }}catch(e){{addMsg('bot','Connection error. Please try again.');}}
}}
</script>
</body></html>"""
    return Response(html, mimetype="text/html")


# Public agent API for embed widgets — uses merchant_id from header, no merchant JWT
@embed_bp.route("/agent", methods=["POST", "OPTIONS"])
@cors_preflight
@rate_limit(
    max_requests=30, window=60,
    key_fn=lambda req: f"embed:{req.headers.get('X-Merchant-Id','x')}:{(req.headers.get('X-Forwarded-For','') or req.remote_addr or 'x').split(',')[0].strip()}"
)
def embed_agent():
    merchant_id = request.headers.get("X-Merchant-Id", "")
    if not merchant_id:
        raise ApiError("X-Merchant-Id header is required.", 400, code="MISSING_MERCHANT")

    body    = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        raise ApiError("'message' is required.", 400, code="MISSING_FIELD")

    from commerce.chat_service import process_message
    result = process_message(merchant_id, message, session_id=body.get("session_id"))
    return api_response(data=result)


# ─────────────────────────────────────────────────────────────────────
# Admin Dashboard
# ─────────────────────────────────────────────────────────────────────

admin_bp = Blueprint("admin_panel", __name__, url_prefix="/api/admin")


def _require_admin():
    """Called at the start of every admin route."""
    from security import get_bearer_token, decode_access_token
    from flask import g
    token   = get_bearer_token()
    payload = decode_access_token(token)
    g.user_id    = payload["sub"]
    g.merchant_id = payload.get("merchant_id")
    user = models.find_user_by_id(g.user_id)
    if not user or user.get("email", "") not in Config.ADMIN_EMAILS:
        raise ApiError("Admin access required.", 403, code="FORBIDDEN")
    return user


@admin_bp.route("/merchants", methods=["GET"])
def admin_merchants():
    _require_admin()
    merchants = models.find_all_merchants()
    return api_response(data={"merchants": [
        {
            "id":            str(m["_id"]),
            "company_name":  m.get("company_name"),
            "merchant_name": m.get("merchant_name"),
            "created_at":    m["created_at"].isoformat() if m.get("created_at") else None,
        }
        for m in merchants
    ], "count": len(merchants)})


@admin_bp.route("/stats", methods=["GET"])
def admin_stats():
    _require_admin()
    merchants  = models.find_all_merchants()
    all_usage  = models.find_all_merchant_usage(limit=500)
    return api_response(data={
        "total_merchants":   len(merchants),
        "usage_records":     len(all_usage),
        "platform": {
            "phase":    5,
            "service":  "ai-commerce-os",
        },
    })


@admin_bp.route("/merchants/<merchant_id>/analytics", methods=["GET"])
def admin_merchant_analytics(merchant_id):
    _require_admin()
    merchant = models.find_merchant_by_id(merchant_id)
    if not merchant:
        raise ApiError("Merchant not found.", 404, code="NOT_FOUND")
    return api_response(data={
        "merchant_id": merchant_id,
        "analytics":   compute_analytics(merchant_id),
    })


@admin_bp.route("/merchants/<merchant_id>/payments", methods=["GET"])
def admin_merchant_payments(merchant_id):
    _require_admin()
    orders = models.find_orders(merchant_id, limit=200)
    return api_response(data={
        "merchant_id": merchant_id,
        "orders":      [
            {"id": str(o["_id"]), "amount": o.get("amount"),
             "status": o.get("status"), "created_at": o["created_at"].isoformat() if o.get("created_at") else None}
            for o in orders
        ],
    })


@admin_bp.route("/merchants/<merchant_id>/workflows", methods=["GET"])
def admin_merchant_workflows(merchant_id):
    _require_admin()
    workflows = models.find_workflows(merchant_id, limit=50)
    return api_response(data={
        "merchant_id": merchant_id,
        "workflow_count": models.count_workflows(merchant_id),
        "workflows": [
            {"id": str(w["_id"]), "name": w.get("name"), "status": w.get("status")}
            for w in workflows
        ],
    })
