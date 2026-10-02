const R={
esc:s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])),
toast(m,ok){const t=document.createElement('div');t.className='toast'+(ok?' ok':'');t.textContent=m;document.body.appendChild(t);setTimeout(()=>t.remove(),3500)},
form(o){const f=new FormData();for(const k in o)f.append(k,o[k]);return{method:'POST',body:f}},
async api(p,o,quiet){let r;try{r=await fetch('/api/v1'+p,Object.assign({credentials:'same-origin'},o))}catch(e){R.toast('Cannot reach the server. Check that the app is running.');throw e}
const j=await r.json().catch(()=>({}));if(!r.ok){let m=j.detail;if(Array.isArray(m))m=(m[0]&&m[0].msg)||'Please check the form and try again.';m=m||'Something went wrong.';if(!quiet)R.toast(m);throw Object.assign(new Error(m),{status:r.status})}return j}};
document.addEventListener('DOMContentLoaded',()=>{const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}}),{threshold:.1});document.querySelectorAll('.rv').forEach(e=>io.observe(e))});
