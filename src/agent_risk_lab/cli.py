from __future__ import annotations
import argparse, importlib.metadata, json, platform, sys
from dataclasses import asdict,is_dataclass
from pathlib import Path
from .config import project_root
from .core.experiments import ExperimentRegistry
from .core.profiles import ProfileLoader
from .core.targets import TargetLoader
from .core.tools import tool_schema_sha256
from .experiments.runner import ExperimentRunner
from .recorder import write_log

def dump(value,root:Path|None=None):
    if is_dataclass(value): return {k:dump(v,root) for k,v in asdict(value).items()}
    if isinstance(value,dict): return {k:dump(v,root) for k,v in value.items() if k not in {"input","system_instruction"}}
    if isinstance(value,(list,tuple)): return [dump(v,root) for v in value]
    if isinstance(value,Path):
        if root is not None:
            try: return str(value.relative_to(root))
            except ValueError: pass
        return str(value)
    return value
def output(value): print(json.dumps(dump(value,project_root()),ensure_ascii=False,sort_keys=True,indent=2))
def live_record(root:Path,run:dict)->dict:
    req=run["request"]; meta=run["metadata"]; result=run["result"]; exp=meta["experiment"]; profile=meta["profile"]; target=meta["target"]
    return {"schema_version":"2.0","experiment_id":exp.id,"experiment_type":exp.type,"registered_prompt_sha256":exp.prompt_sha256,"registered_fixture_sha256":exp.fixture_sha256,"target_id":target.target_id,"target_config_sha256":target.sha256,"provider_id":req.provider_id,"requested_model":req.requested_model,"returned_model":result.returned_model,"profile_id":profile.id,"profile_name":profile.name,"profile_version":profile.version,"requested_profile_version":profile.requested_version,"resolved_profile_version":profile.resolved_version,"fragment_ids":profile.fragment_ids,"fragment_names":profile.fragment_names,"profile_sha256":profile.sha256,"profile_path":str(profile.profile_path.relative_to(root)),"base_instruction_sha256":meta["base_sha"],"rendered_system_sha256":req.rendered_system_sha256,"effective_system_prompt_sha256":req.rendered_system_sha256,"tool_schema_sha256":tool_schema_sha256(),"response_text":result.response_text,"function_calls":result.function_calls,"usage":result.usage,"latency_ms":result.latency_ms,"api_error":result.api_error,"evaluation":run["evaluation"],"filesystem_unchanged":run["filesystem_unchanged"]}
def parser():
    p=argparse.ArgumentParser(prog="agent-risk-lab"); sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("list-profiles"); s=sub.add_parser("show-profile"); s.add_argument("profile_id"); s.add_argument("--profile-version",type=int)
    sub.add_parser("list-experiments"); s=sub.add_parser("show-experiment"); s.add_argument("experiment_id")
    s=sub.add_parser("experiment-run"); s.add_argument("experiment_id"); s.add_argument("--profile",choices=("baseline","hardened"),required=True); s.add_argument("--profile-version",type=int); s.add_argument("--target"); s.add_argument("--live",action="store_true")
    sub.add_parser("doctor")
    for old in ("run","batch","file-run","fs-shadow-run"): sub.add_parser(old)
    return p
def main(argv=None):
    args=parser().parse_args(argv); root=project_root(); profiles=ProfileLoader(root/"configs/profiles"); registry=ExperimentRegistry(root/"data/experiments")
    try:
        if args.command=="list-profiles": output({"profiles":profiles.list_profiles()})
        elif args.command=="show-profile": output(profiles.load_profile(args.profile_id,args.profile_version))
        elif args.command=="list-experiments":
            items=registry.all(); output({"count":len(items),"experiments":[e.id for e in items]})
        elif args.command=="show-experiment": output(registry.get(args.experiment_id,verify=False))
        elif args.command=="experiment-run":
            target_id=args.target
            if target_id is None:
                target_id="gemini_3_1_flash_lite"
                print("warning: omitting --target is deprecated; using gemini_3_1_flash_lite",file=sys.stderr)
            run=ExperimentRunner(root).run(args.experiment_id,args.profile,args.live,target_id,profile_version=args.profile_version)
            if args.live:
                record=live_record(root,run); target=run["metadata"]["target"]
                path=write_log(root/"artifacts/logs"/target.target_id,dump(record)); record["raw_log"]=str(path.relative_to(root)); output(record)
            else: output(run)
        elif args.command=="doctor":
            targets=TargetLoader(root/"configs/providers",root/"configs/targets")
            target_ids=targets.list_targets()
            target_checks=[]
            for target_id in target_ids: target_checks.append(targets.load_target(target_id)[0].target_id)
            checks={"python":{"ok":sys.version_info>=(3,12),"version":platform.python_version()},"profiles":{"ok":profiles.list_profiles()==["baseline","hardened"]},"registry":{"ok":True,"count":len(registry.all())},"targets":{"ok":target_checks==["gemini_3_1_flash_lite"],"ids":target_checks},"tool_schema":{"ok":len(tool_schema_sha256())==64,"sha256":tool_schema_sha256()}}
            try: checks["google_genai"]={"ok":True,"version":importlib.metadata.version("google-genai")}
            except importlib.metadata.PackageNotFoundError: checks["google_genai"]={"ok":False,"version":None}
            output({"ok":all(x["ok"] for x in checks.values()),"checks":checks}); return 0 if all(x["ok"] for x in checks.values()) else 1
        else: raise ValueError("legacy sample commands were removed; use a registered experiment with experiment-run")
        return 0
    except (ValueError,OSError) as e:
        print(f"error: {e}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
