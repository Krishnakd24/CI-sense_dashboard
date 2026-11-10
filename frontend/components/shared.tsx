"use client";
import { Loader2 } from "lucide-react";
export const API=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
export type Data=Record<string,unknown>;
export type Stage={status?:string;[key:string]:unknown};
export type PredictionResult={status:string;reasons?:string[];flaky_probability?:number;message?:string;technical_error?:string;model_reference?:Data;prompt_sha256?:string};
export type Test={prediction:PredictionResult;id:string;name:string;selected:boolean;xml:Data;xml_state:Stage;source:Stage;failure_reports:Record<string,string>[];payload:Data|null;payload_state:{status:string;issues?:string[]};payload_reference:Data|null};
export type Analysis={id:string;repository:string;commit:string;parent_commit?:string|null;admin_test:boolean;project_id:string|null;status:string;created_at:string;message?:string;technical_error?:string;diff:Stage;tests:Test[]};
export type Task=(fn:()=>Promise<void>)=>Promise<void>;
export async function api<T>(path:string,init?:RequestInit):Promise<T>{
 const r=await fetch(API+path,{credentials:"include",...init});const data=await r.json().catch(()=>({detail:"Unexpected server response."}));
 if(!r.ok)throw new Error(typeof data.detail==="string"?data.detail:"Request validation failed.");return data;
}
export const json=(method:string,body:unknown):RequestInit=>({method,headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
export function Status({value="pending"}:{value?:string}){return <span className={"pill "+value}>{value==="running"&&<Loader2 size={12} className="spinner"/>}{value.replaceAll("_"," ")}</span>}
export function Code({value}:{value:unknown}){return <pre><code>{typeof value==="string"?value:JSON.stringify(value,null,2)}</code></pre>}
export function Field({label,children}:{label:string;children:React.ReactNode}){return <label className="field"><span className="hint">{label}</span>{children}</label>}
