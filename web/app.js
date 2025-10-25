(function(){
  const $ = (id)=>document.getElementById(id)
  const origin = window.location.origin
  ;['origin1','origin2','origin3'].forEach(id=>{$(id).textContent=origin})

  function fmtUptime(sec){
    const s = Math.floor(sec%60)
    const m = Math.floor((sec/60)%60)
    const h = Math.floor((sec/3600)%24)
    const d = Math.floor(sec/86400)
    const parts=[]
    if(d) parts.push(d+"d")
    if(h) parts.push(h+"h")
    if(m) parts.push(m+"m")
    parts.push(s+"s")
    return parts.join(" ")
  }

  async function refresh(){
    try{
      const r = await fetch(origin+"/healthz", {headers:{'Cache-Control':'no-cache'}})
      if(!r.ok) throw new Error("http "+r.status)
      const h = await r.json()
      $("st").textContent = h.status
      $("uptime").textContent = fmtUptime(h.uptime_seconds||0)
      $("queue").textContent = `${h.queue_size}/${h.queue_capacity}`
      $("workers").textContent = `${h.running_workers}/${h.max_workers}`
      $("backend").textContent = h.compute_backend || 'unknown'
      const g = (h.gpu_free_gb!=null && h.gpu_total_gb!=null) ? `${h.gpu_free_gb.toFixed(2)}/${h.gpu_total_gb.toFixed(2)} GB` : 'n/a'
      $("gpu").textContent = g

      $("model-enabled").textContent = h.model_enabled ? '已启用' : '未启用'
      $("model-tip").textContent = h.model_enabled ? '任务接口可用' : '已通过 APP_ENABLE_DS_MODEL=false 禁用模型，任务接口将返回 503'

      $("mcp-enabled").textContent = h.mcp_enabled ? '已启用' : '未启用'
      if(h.mcp_enabled){
        $("mcp-how").innerHTML = `
<pre><code>pip install -r requirements.txt
DSOCR_BASE_URL=${origin} DSOCR_API_KEY=sk_xxx python mcp/dsocr_mcp.py
</code></pre>`
      } else {
        $("mcp-how").textContent = '如需提示 MCP，可设置 APP_ENABLE_MCP=true（服务侧元信息），并在客户端以子进程启动 mcp/dsocr_mcp.py'
      }
    }catch(e){
      $("st").textContent = 'unreachable'
      $("model-tip").textContent = String(e)
    }
  }

  refresh()
  setInterval(refresh, 10000)
})();

