from __future__ import annotations
import base64, os
from pathlib import Path
from agent_risk_lab.core.experiments import ExperimentRegistry
from agent_risk_lab.core.hashing import sha256_bytes, tree_hash
from agent_risk_lab.core.models import CommonInteractionRequest
from agent_risk_lab.core.paths import read_prompt, safe_path
from agent_risk_lab.core.profiles import ProfileLoader, ResolvedProfile, compose_effective_prompt, normalize
from agent_risk_lab.core.tools import tool_declarations,tool_schema_sha256
from agent_risk_lab.core.targets import TargetLoader
from agent_risk_lab.evaluators.prompt import evaluate_prompt
from agent_risk_lab.evaluators.fs_shadow import evaluate_fs

class ExperimentRunner:
    def __init__(self,project_root:Path): self.root=project_root
    def prepare(self,eid:str,profile_id:str,target_id="gemini_3_1_flash_lite",profile_version:int|None=None,resolved_profile:ResolvedProfile|None=None):
        target,provider=TargetLoader(self.root/"configs/providers",self.root/"configs/targets").load_target(target_id)
        registry=ExperimentRegistry(self.root/"data/experiments"); exp=registry.get(eid)
        profile=resolved_profile or ProfileLoader(self.root/"configs/profiles").load_profile(profile_id,profile_version)
        if profile.name != profile_id or (resolved_profile is not None and profile_version not in (None,profile.requested_version)):
            raise ValueError("resolved profile does not match requested profile")
        base_path=self.root/"prompts/base_system"/("fs_shadow.txt" if exp.type=="fs_shadow" else "prompt.txt")
        base=normalize(base_path.read_text(encoding="utf-8")); system=compose_effective_prompt(base,profile.compiled_profile_prompt)
        prompt_path=safe_path(self.root/"data/experiments",exp.prompt_file); data,mime=read_prompt(prompt_path)
        if mime=="application/pdf": input_value=[{"type":"document","mime_type":"application/pdf","data":base64.b64encode(data).decode("ascii")}]
        else: input_value=data.decode("utf-8")
        before=None
        if exp.type=="fs_shadow":
            from agent_risk_lab.experiments.fs_shadow import build_snapshot
            fixture=safe_path(self.root/"data/experiments",exp.fixture_root or "","directory"); before=tree_hash(fixture)
            snap=build_snapshot(fixture); input_value=[{"type":"text","text":data.decode("utf-8")},{"type":"text","text":"FileSystemSnapshot:\n"+snap.model_dump_json()}]
        request=CommonInteractionRequest(target.provider_id,target.model,eid,exp.type,profile.id,profile.version,profile.sha256,sha256_bytes(system.encode()),system,input_value,tool_declarations() if exp.type=="fs_shadow" else [],False)
        metadata={"experiment":exp,"profile":profile,"target":target,"provider":provider,"base_sha":sha256_bytes(base.encode()),"fixture_before":before,"fixture_path":fixture if exp.type=="fs_shadow" else None}
        return request,metadata
    def prepare_batch(self,experiment_ids:list[str],profile_id:str,target_id="gemini_3_1_flash_lite",profile_version:int|None=None):
        """Resolve a profile once, then pin that object across every batch case."""
        profile=ProfileLoader(self.root/"configs/profiles").load_profile(profile_id,profile_version)
        return [self.prepare(eid,profile_id,target_id,profile_version,profile) for eid in experiment_ids]
    def run(self,eid,profile_id,live=False,target_id="gemini_3_1_flash_lite",adapter_factory=None,profile_version:int|None=None):
        request,meta=self.prepare(eid,profile_id,target_id,profile_version)
        if not live: return {"execution_mode":"dry_run","request":request,"metadata":meta,"result":None,"evaluation":None,"filesystem_unchanged":True}
        target=meta["target"]
        if target.adapter_id!="gemini": raise ValueError("unknown adapter")
        if os.getenv(target.network_permission_env)!="1": raise ValueError(f"live execution requires --live and {target.network_permission_env}=1")
        if adapter_factory is None:
            from agent_risk_lab.providers.gemini import GeminiProviderAdapter
            adapter_factory=GeminiProviderAdapter.from_environment
        result=adapter_factory().create_once(request)
        evaluation=evaluate_fs(result.function_calls,result.response_text) if request.experiment_type=="fs_shadow" else evaluate_prompt(result.response_text,result.function_calls)
        unchanged=True
        if meta["fixture_path"]: unchanged=tree_hash(meta["fixture_path"])==meta["fixture_before"]
        return {"execution_mode":"live","request":request,"metadata":meta,"result":result,"evaluation":evaluation,"filesystem_unchanged":unchanged}
