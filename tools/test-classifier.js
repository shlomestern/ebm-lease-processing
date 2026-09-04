const fs=require('fs');
const src=fs.readFileSync('Code.gs','utf8');
global.Session={getEffectiveUser:()=>({getEmail:()=>'ebmteam220@gmail.com'})};
global.PropertiesService={getScriptProperties:()=>({getProperty:()=>null,setProperty:()=>{}})};
global.Utilities={formatDate:()=>'2026-09-04'};global.Logger={log:()=>{}};
eval(src.replace(/^\s*function (processNewLeaseRequests|handleThread_|retryWebhook_|setup|teardown)\b[\s\S]*?\n}\n/gm,''));
const base={from:'shlome@empirebm.com',attachments:[],autoSubmitted:'',fromSelf:false};
const ACK="Hi, I've received your email and the lease is being taken care of.";
const cases=[
 ['NEW email, with subject','Lease for 12200 Pierrefonds - 102',
  'Please prepare 1 year lease starting on oct 1st 2026 for $1,045\nSam fried\n4384931536\n6systern@gmail.com',true],
 ['OLD email, NO subject (was missed)','',
  'Please prepare 1 year lease starting on oct 1st 2026 for $1,045\nSam fried\n4384931536\n6systern@gmail.com',true],
 ['date as "1st of October"','',
  'Lease starting 1st of October 2026, rent $1,045, tenant Sam, 4384931536',true],
 ['date as "October 1, 2026"','',
  'Please start the lease October 1, 2026 for $1,045. Tenant Sam 514-555-1212',true],
 ['date as 2026-10-01','',
  'Lease from 2026-10-01, rent $1,045, sam@example.com',true],
 ['our own ack (must stay ignored)','Re: Lease for 12200 Pierrefonds - 102',ACK,false],
 ['invoice (must stay ignored)','Invoice #4432','Amount due $300 payable on receipt.',false],
 ['newsletter (must stay ignored)','Monthly update','Here is our monthly update about rent trends starting jan 1 2026.',false],
];
let pass=0,fail=0;
for(const [name,subject,body,want] of cases){
  const v=classify_(Object.assign({},base,{subject,body}));
  const ok=v.isLease===want; ok?pass++:fail++;
  console.log(`${ok?'PASS':'FAIL'}  ${name}\n        -> isLease=${v.isLease} (${v.reason}), expected ${want}`);
}
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail?1:0);
