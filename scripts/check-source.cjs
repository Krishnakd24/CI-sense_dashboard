// Static repository checks only; this is NOT a build or a runtime test.
const fs=require('fs'),path=require('path'),assert=require('assert');
const root=path.resolve(__dirname,'..');
for(const p of ['frontend/package.json','frontend/tsconfig.json'])JSON.parse(fs.readFileSync(path.join(root,p),'utf8'));
for(const p of ['frontend/app/page.tsx','backend/app/main.py','backend/migrations/versions/0001_layer1.py','README.md','.env.example']){
 assert(fs.statSync(path.join(root,p)).size>0,p+' is missing or empty');
}
const pipeline=fs.readFileSync(path.join(root,'backend/app/pipeline.py'),'utf8');
assert(!/invoke\([^\n]*classifier/.test(pipeline),'Layer 2 must not be invoked');
assert(pipeline.includes('test.xml'),'Original parsed evidence must be used to assemble the research payload');
const config=fs.readFileSync(path.join(root,'backend/app/main.py'),'utf8');
assert(config.includes('key_configured'),'Only key status should be exposed');
assert(config.includes('RequestValidationError'),'Validation errors must not echo submitted API keys');
assert(config.includes('Depends(admin)'),'Admin routes require backend authorization');
let files=0;
function walk(dir){for(const item of fs.readdirSync(dir,{withFileTypes:true})){if(['node_modules','.next','.venv','__pycache__'].includes(item.name))continue;const p=path.join(dir,item.name);if(item.isDirectory())walk(p);else files++;}}
walk(root);
console.log('Static repository checks passed ('+files+' files). No Python execution, TypeScript typecheck, browser QA or live integration is implied.');
