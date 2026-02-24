// todoist-runner.js - TODOIST DAILY REVIEW AUTOMATION
// Run from app.todoist.com tab via Claude or browser console.
// Fetches overdue + undated tasks by PARA area, then registers
// window._todoistExecute() for batch updates.
//
// Tell Claude: "1->today, 2,3->friday, 4->complete, 5->skip"
// Dates: today, tomorrow, friday, saturday, monday/next week, YYYY-MM-DD
// Actions: complete/done/c, skip/s, no date

(async () => {
    const API_KEY = 'c48f86e2730782b3b263e45b3f589ccad89e5b66';
    const PARA = ['PROSPER \u{1F4C1}','WORK \u{1F4C1}','HEALTH \u{1F4C1}','PERSONAL & FAMILY \u{1F4C1}','HOME \u{1F4C1}','FINANCIAL \u{1F4C1}','FUN \u{1F4C1}'];

   const r = await fetch('https://app.todoist.com/api/v1/sync', {
         method: 'POST',
         headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_KEY}` },
         body: JSON.stringify({ sync_token: '*', resource_types: ['items'] })
   });
    const { items = [] } = await r.json();
    const today = new Date(); today.setHours(0,0,0,0);
    const todayStr = today.toISOString().split('T')[0];
    const tasks = items.filter(t => !t.checked && !t.is_deleted);

   const overdue = [], undated = [];
    for (const t of tasks) {
          const para = t.labels.find(l => PARA.includes(l));
          if (!para) continue;
          if (!t.due) undated.push({...t, _para: para});
          else if (t.due.date.split('T')[0] < todayStr) overdue.push({...t, _para: para});
    }

   let n = 1; const lines = [], idx = {};
    for (const label of PARA) {
          const od = overdue.filter(t => t._para === label);
          const ud = undated.filter(t => t._para === label);
          if (od.length) { lines.push(`\n\u{1F4CB} ${label} - OVERDUE`); od.forEach(t => { lines.push(`  ${n}. [${t.due.date}] ${t.content}`); idx[n++] = t.id; }); }
          if (ud.length) { lines.push(`\n\u{1F4CB} ${label} - NO DATE`); ud.forEach(t => { lines.push(`  ${n}. ${t.content}`); idx[n++] = t.id; }); }
    }
    window._todoistReview = { overdue, undated, allTasks: tasks };
    window._todoistIndexMap = idx;

   function toDate(v) {
         const d = new Date(today), s = v.toLowerCase().trim();
         if (s === 'today') return todayStr;
         if (s === 'tomorrow') { d.setDate(d.getDate()+1); return d.toISOString().split('T')[0]; }
         if (s === 'friday') { d.setDate(d.getDate()+((5-d.getDay()+7)%7||7)); return d.toISOString().split('T')[0]; }
         if (['saturday','weekend'].includes(s)) { d.setDate(d.getDate()+((6-d.getDay()+7)%7||7)); return d.toISOString().split('T')[0]; }
         if (['monday','next week'].includes(s)) { d.setDate(d.getDate()+((8-d.getDay())%7||7)); return d.toISOString().split('T')[0]; }
         return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : null;
   }

   window._todoistExecute = async function(instr) {
         const parsed = {};
         if (typeof instr === 'string') {
                 instr.split(/(?<=[a-z0-9])\s*,\s*(?=\d)/i).forEach(seg => {
                           const m = seg.trim().match(/^([\d\s,]+)[\u2192\->=:]+(.+)$/);
                           if (m) m[1].split(/[,\s]+/).filter(Boolean).forEach(k => (parsed[k.trim()] = m[2].trim()));
                 });
         } else Object.assign(parsed, instr);
         const cmds = [], res = [];
         for (const [k, act] of Object.entries(parsed)) {
                 const id = idx[k]; if (!id) { res.push(`Not found: #${k}`); continue; }
                 const uuid = crypto.randomUUID(), lo = act.toLowerCase().trim();
                 if (['skip','s'].includes(lo)) { res.push(`Skipped #${k}`); continue; }
                 if (['complete','done','c'].includes(lo)) { cmds.push({type:'item_close',uuid,args:{id}}); res.push(`Done #${k}`); continue; }
                 if (['no date','nodate'].includes(lo)) { cmds.push({type:'item_update',uuid,args:{id,due:null}}); res.push(`No date #${k}`); continue; }
                 const date = toDate(act);
                 if (date) { cmds.push({type:'item_update',uuid,args:{id,due:{date}}}); res.push(`#${k}->${date}`); }
                 else res.push(`Unknown: "${act}" #${k}`);
         }
         if (!cmds.length) return {message:'Nothing to execute',results:res};
         const resp = await fetch('https://app.todoist.com/api/v1/sync', {
                 method:'POST', headers:{'Content-Type':'application/json','Authorization':`Bearer ${API_KEY}`},
                 body: JSON.stringify({commands:cmds})
         });
         const json = await resp.json();
         const ok = Object.values(json.sync_status||{}).every(v=>v==='ok');
         console.log(`${ok?'OK':'WARN'} ${cmds.length} updates: `+res.join(', '));
         return {status:resp.status,allOk:ok,results:res};
   };

   const out = `\nTODOIST DAILY REVIEW - ${todayStr}\nOverdue: ${overdue.length} | No date: ${undated.length} | Total: ${overdue.length+undated.length}\n${'='.repeat(50)}`+lines.join('\n')+'\n\nTell Claude: "1->today, 2->friday, 3->complete"';
    console.log(out); return out;
})();
