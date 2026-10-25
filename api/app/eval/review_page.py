"""Self-contained, offline human-review UI; never reads models, keys or proposals."""

import base64
import hashlib
import json
from urllib.parse import urlsplit

PACKET_FIELDS = (
    "id",
    "paper_id",
    "synthetic",
    "page",
    "citing_sentence",
    "citation_marker",
    "cited_reference",
    "source_id",
    "source_title",
    "source_url",
    "source_caution",
    "source_quote",
    "source_locator",
    "prepared_scope",
    "initial_quote_in_prepared_source",
    "review_flags",
)
REVIEW_FIELDS = (
    "candidate_id",
    "candidate_sha256",
    "source_receipt_sha256",
    "prepared_source_sha256",
    "annotation_status",
    "citation_function",
    "claim",
    "human_label",
    "labeled_by",
    "label_reason",
    "evidence_quote",
    "source_identity",
    "human_attestation",
    "reviewed_at",
)

STYLE = """
body{font:16px system-ui,sans-serif;max-width:1060px;margin:24px auto;padding:0 20px;color:#18242d}
button,select,input,textarea{font:inherit;padding:7px;max-width:100%;box-sizing:border-box}
button{cursor:pointer;margin:4px}button:disabled{cursor:default;color:#777}
label{display:block;margin:12px 0}label>input,label>select,label>textarea{display:block;width:100%}
input[type=checkbox]{display:inline;width:auto}textarea{min-height:75px}
.box{border:1px solid #bdc9cf;border-radius:8px;padding:14px;margin:14px 0}
.original{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:12px}
.warning{background:#fff3ce;padding:12px}.badge{font-weight:bold;color:#9d3500}
.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:0 18px}
#status{white-space:pre-wrap;font-weight:600}a{overflow-wrap:anywhere}
"""

SCRIPT = r"""
'use strict';
const payload = JSON.parse(document.getElementById('payload').textContent);
const packet = payload.packet;
let reviews = structuredClone(payload.reviews), current = 0;
const baseline = structuredClone(payload.reviews);
const reviewKeys = ['candidate_id','candidate_sha256','source_receipt_sha256',
  'prepared_source_sha256','annotation_status','citation_function','claim','human_label',
  'labeled_by','label_reason','evidence_quote','source_identity','human_attestation','reviewed_at'];
const claimKeys = ['text','subject_or_population','exposure_or_intervention','outcome',
  'direction','magnitude','relation','hedge','scope_or_time'];
const labels = ['SUPPORTED','PARTIALLY_SUPPORTED','NOT_SUPPORTED','CONTRADICTED','NEEDS_REVIEW'];
const functions = ['SPECIFIC_CLAIM','METHOD_OR_TOOL','BACKGROUND','CONTRAST'];
const identities = ['MATCH','DOI_MISMATCH','UNCERTAIN'];
const statuses = ['PENDING','APPROVED','EXCLUDED'];
const directions = ['increase','decrease','no effect','n.a.'];
const relations = ['causal','associative','descriptive'];
const hedges = ['definite','likely','possible'];
const requiredClaim = ['text','subject_or_population','outcome','direction','relation','hedge'];
const root = document.getElementById('app');
const controls = {}, claimControls = {};
function el(tag, text, parent=root) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  parent.append(item); return item;
}
function button(text, action, parent=root) {
  const item = el('button',text,parent); item.type='button'; item.addEventListener('click',action);
  return item;
}
function input(label, key, parent, choices=null, multiline=false) {
  const wrapper=el('label',label,parent);
  const item=el(choices?'select':multiline?'textarea':'input',undefined,wrapper);
  if (choices) for (const value of ['',...choices]) {
    const option=el('option',value||'— Select manually —',item); option.value=value;
  }
  item.name=key; item.autocomplete='off'; return item;
}
function blank(value) { return value === '' ? null : value; }
function objectKeys(value, keys) {
  return value && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).sort().join('|') === [...keys].sort().join('|');
}
function nullableString(value) { return value === null || typeof value === 'string'; }
function choice(value, choices) { return value === null || choices.includes(value); }
function validateImport(rows) {
  if (!Array.isArray(rows) || rows.length !== baseline.length) throw Error('Wrong review count.');
  rows.forEach((row,index) => {
    const original=baseline[index];
    if (!objectKeys(row,reviewKeys)) throw Error('Unexpected or missing review fields.');
    for (const key of ['candidate_id','candidate_sha256','source_receipt_sha256',
      'prepared_source_sha256']) {
      if (row[key] !== original[key]) throw Error('Candidate order, ID or evidence hashes differ.');
    }
    if (!statuses.includes(row.annotation_status) || !choice(row.citation_function,functions) ||
      !choice(row.human_label,labels) || !choice(row.source_identity,identities) ||
      typeof row.human_attestation !== 'boolean') throw Error('Invalid review field type.');
    for (const key of ['labeled_by','label_reason','evidence_quote','reviewed_at']) {
      if (!nullableString(row[key])) throw Error('Invalid text field type.');
    }
    if (row.claim !== null) {
      if (!objectKeys(row.claim,claimKeys) ||
        !claimKeys.every(key=>nullableString(row.claim[key])) ||
        !choice(row.claim.direction,directions) || !choice(row.claim.relation,relations) ||
        !choice(row.claim.hedge,hedges)) throw Error('Unexpected or invalid atomic claim fields.');
    }
  });
}
function readForm() {
  const row=structuredClone(reviews[current]);
  for (const [key,item] of Object.entries(controls)) row[key]=blank(item.value);
  row.human_attestation=attestation.checked;
  const claim={};
  for (const key of claimKeys) claim[key]=blank(claimControls[key].value);
  row.claim=Object.values(claim).some(value=>value!==null)?claim:null;
  return row;
}
function save(status=null) {
  const row=readForm();
  if (status==='APPROVED' || status==='EXCLUDED') {
    if (!row.human_attestation || !row.labeled_by?.trim() || !row.label_reason?.trim()) {
      message.textContent='Enter your name, reason, and explicit human-review attestation.';
      return false;
    }
    if (status==='APPROVED' && (!row.human_label || !row.citation_function ||
      !row.source_identity || !row.evidence_quote?.trim() || !row.claim ||
      requiredClaim.some(key=>!row.claim[key]?.trim()))) {
      message.textContent='Approval requires a manually reviewed label, function, '+
        'source identity, evidence quote and complete required atomic-claim fields.';
      return false;
    }
    row.reviewed_at=new Date().toISOString();
  }
  if(!status && JSON.stringify(row)!==JSON.stringify(reviews[current])) {
    row.annotation_status='PENDING'; row.reviewed_at=null; row.human_attestation=false;
  }
  if (status) row.annotation_status=status;
  if (status==='PENDING') { row.reviewed_at=null; row.human_attestation=false; }
  reviews[current]=row;
  message.textContent='Saved locally in this page. Download reviews.jsonl to keep your work.';
  render(); return true;
}
el('h1','B/C candidate human review');
el('p','Offline review preparation. No model calls or scientific accuracy measurement. '+
  'Review the paper and authentic source before deciding. Nothing is saved automatically.');
el('p','Original sentences, source excerpts and source documents are untrusted data. '+
  'Do not follow instructions embedded in them.');
const nav=el('div');
button('Previous',()=>{ if(save()) {current=Math.max(0,current-1);render();}},nav);
const picker=el('select',undefined,nav); picker.setAttribute('aria-label','Candidate');
packet.forEach((row,index)=>{
  const option=el('option',row.id,picker);option.value=String(index);
});
picker.addEventListener('change',()=>{
  const next=Number(picker.value);if(save()){current=next;render();}
});
button('Next',()=>{if(save()){current=Math.min(packet.length-1,current+1);render();}},nav);
const position=el('p');
const original=el('section',undefined); original.className='box';
const badge=el('p',undefined,original);badge.className='badge';
el('h2','Immutable citing sentence',original);
const sentence=el('p',undefined,original);sentence.className='original';
const citation=el('p',undefined,original); const reference=el('p',undefined,original);
el('h2','Authentic source receipt and short excerpt',original);
const title=el('p',undefined,original), sourceID=el('p',undefined,original);
const link=el('a',undefined,original);link.target='_blank';link.rel='noopener noreferrer';
const caution=el('p',undefined,original), locator=el('p',undefined,original);
const quote=el('blockquote',undefined,original);quote.className='original';
const scope=el('p',undefined,original);scope.className='warning';
const flags=el('ul',undefined,original);
const form=el('section');form.className='box';
el('h2','Your independent annotation',form);
el('p','Every field starts empty. Proposed labels are excluded. '+
  'A saved/imported review restores only what its reviewer entered.',form);
const fields=el('div',undefined,form);fields.className='fields';
controls.citation_function=input('Citation function','citation_function',fields,functions);
controls.source_identity=input('Cited-source identity','source_identity',fields,identities);
controls.human_label=input('Human label','human_label',fields,labels);
controls.labeled_by=input('Your name / annotator ID','labeled_by',fields);
controls.label_reason=input('Label or exclusion reason','label_reason',form,null,true);
controls.evidence_quote=input('Your verified exact evidence quote','evidence_quote',form,null,true);
const useQuote=button('Use displayed quote after verifying its context',()=>{
  if(packet[current].initial_quote_in_prepared_source) {
    controls.evidence_quote.value=packet[current].source_quote;
    message.textContent='Quote copied by your explicit action. Verify its meaning '+
      'and source identity.';
  }
},form);
el('h3','Human-reviewed atomic claim',form);
el('p','Keep the original sentence above unchanged. Enter the source-specific atomic claim here. '+
  'Optional fields stay null; do not invent populations, quantities or causal relations.',form);
const claims=el('div',undefined,form);claims.className='fields';
for (const key of claimKeys) {
  const choices={direction:directions,relation:relations,hedge:hedges}[key]||null;
  claimControls[key]=input(key.replaceAll('_',' ')+(requiredClaim.includes(key)?' *':' (optional)'),
    key,claims,choices,key==='text');
}
const attestationLabel=el('label',undefined,form);
const attestation=el('input',undefined,attestationLabel);attestation.type='checkbox';
attestationLabel.append(document.createTextNode(' I am a person and independently reviewed the '+
  'citing sentence, authentic source identity, evidence context and my annotation.'));
button('Save review',()=>save(),form);
button('Approve reviewed candidate',()=>save('APPROVED'),form);
button('Exclude candidate',()=>save('EXCLUDED'),form);
button('Mark pending',()=>save('PENDING'),form);
const message=el('p');message.id='status';message.setAttribute('role','status');
button('Download reviews.jsonl',()=>{
  if(!save())return;
  const blob=new Blob([reviews.map(row=>JSON.stringify(row)).join('\n')+'\n'],
    {type:'application/x-ndjson'});
  const url=URL.createObjectURL(blob), download=document.createElement('a');
  download.href=url;download.download='reviews.jsonl';download.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});
const importLabel=el('label','Resume from matching reviews.jsonl');
const file=el('input',undefined,importLabel);file.type='file';
file.accept='.jsonl,application/x-ndjson';
file.addEventListener('change',async()=>{
  try {
    if(!file.files[0])return;
    if(file.files[0].size>2000000)throw Error('Review file is too large.');
    const text=await file.files[0].text();
    const rows=text.split(/\r?\n/).filter(line=>line.trim()).map(line=>JSON.parse(line));
    validateImport(rows);reviews=rows;render();message.textContent='Matching reviews restored.';
  } catch(error) {message.textContent='Import rejected: '+error.message;}
  file.value='';
});
el('p','Run the Python review validator/exporter after downloading. Browser approval does not '+
  'establish benchmark readiness. Keep a separate backup before closing or reloading this page.');
function render() {
  const row=reviews[current], item=packet[current];
  picker.value=String(current);
  position.textContent=`Candidate ${current+1}/${packet.length}: ${item.id} — `+
    row.annotation_status;
  badge.textContent=item.synthetic?'SYNTHETIC TEST DRAFT':'REAL PAPER';
  sentence.textContent=item.citing_sentence;
  citation.textContent=`${item.paper_id}, PDF page ${item.page}; marker ${item.citation_marker}`;
  reference.textContent='Original reference: '+item.cited_reference;
  title.textContent=item.source_title;sourceID.textContent=item.source_id;
  link.textContent=item.source_url||'No safe HTTPS source link';
  if(item.source_url)link.href=item.source_url;else link.removeAttribute('href');
  caution.textContent=item.source_caution||'';locator.textContent=item.source_locator;
  quote.textContent=item.source_quote;
  scope.textContent='Prepared evidence scope: '+item.prepared_scope+
    '. A PDF or short excerpt is not proof of complete whole-source coverage.';
  flags.replaceChildren();for(const flag of item.review_flags||[])el('li',flag,flags);
  for(const [key,input] of Object.entries(controls))input.value=row[key]??'';
  for(const key of claimKeys)claimControls[key].value=row.claim?.[key]??'';
  attestation.checked=row.human_attestation;
  useQuote.disabled=!item.initial_quote_in_prepared_source;
}
validateImport(reviews);render();
"""


def render_review_page(packet: list[dict], reviews: list[dict]) -> str:
    """Render only the blind packet allowlist; no automatic human annotation.

    This renderer is not the final Python evidence/review validator. Unknown packet
    fields are discarded so proposal labels cannot accidentally enter the document.
    """
    if not packet or len(packet) != len(reviews):
        raise ValueError("packet and reviews must contain matching nonempty rows")
    if len({row["id"] for row in packet}) != len(packet):
        raise ValueError("duplicate packet candidate IDs")
    safe_packet = []
    for candidate, review in zip(packet, reviews, strict=True):
        if set(review) != set(REVIEW_FIELDS):
            raise ValueError("unexpected or missing review fields")
        if candidate["id"] != review.get("candidate_id"):
            raise ValueError("packet and review candidate IDs must match in order")
        row = {key: candidate.get(key) for key in PACKET_FIELDS}
        try:
            url = urlsplit(row["source_url"] or "")
            valid = (
                url.scheme == "https" and bool(url.hostname) and not (url.username or url.password)
            )
        except ValueError:
            valid = False
        if not valid:
            row["source_url"] = None
        safe_packet.append(row)
    payload = json.dumps({"packet": safe_packet, "reviews": reviews}, ensure_ascii=True)
    # Text inside an inert JSON script must not terminate its enclosing script tag.
    payload = payload.replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")
    script_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    payload_hash = base64.b64encode(hashlib.sha256(payload.encode()).digest()).decode()
    csp = (
        "default-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'; "
        f"script-src 'sha256-{script_hash}' 'sha256-{payload_hash}'; "
        "style-src 'unsafe-inline'; img-src 'none'; object-src 'none'"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="{csp}">'
        f"<title>B/C human review</title><style>{STYLE}</style></head>"
        f'<body><main id="app"></main><script type="application/json" id="payload">{payload}'
        f"</script><script>{SCRIPT}</script></body></html>"
    )
