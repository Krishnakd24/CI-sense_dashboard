"use client";
import { useState } from "react";
import { Copy, Download } from "lucide-react";
import { Button } from "./ui/button";
import { Code, type Test } from "./shared";

export function PayloadPanel({test}:{test:Test}){
 const [copied,setCopied]=useState(false),[copyError,setCopyError]=useState("");
 if(!test.payload)return <div className="notice"><h3>B2_o1 JSON is not ready</h3><p>All required evidence must be available before a model input can be assembled.</p>
 <ul>{(test.payload_state.issues||["Complete extraction and resolve any component issues."]).map(issue=><li key={issue}>{issue}</li>)}</ul></div>;
 const text=JSON.stringify(test.payload,null,2);
 function download(){const url=URL.createObjectURL(new Blob([text+"\n"],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download="b2_o1-evidence.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),0)}
 return <><div className="row spread"><div><h3>Final B2_o1 JSON</h3><p className="hint">Exact target fields: test_code, failure_reports, project_change_description.</p></div><div className="row">
 <Button variant="outline" onClick={async()=>{try{await navigator.clipboard.writeText(text);setCopied(true);setCopyError("")}catch{setCopyError("Copy was unavailable. Use Download JSON.")}}}><Copy size={14}/>{copied?"Copied":"Copy"}</Button>
 <Button variant="outline" onClick={download}><Download size={14}/>Download JSON</Button></div></div>
 {copyError&&<p role="alert">{copyError}</p>}<Code value={test.payload}/>
 <details><summary>Saved payload provenance</summary><Code value={test.payload_reference}/></details>
 <p className="hint">Application IDs, commit metadata and status fields are excluded from this JSON. The central classifier returns a probability from 0 to 1.</p></>;
}
