from agent_risk_lab.core.models import CommonInteractionRequest
from agent_risk_lab.core.tools import tool_declarations
from gemini_injection_lab.client import GeminiProviderAdapter
def test_nine_tools(): assert len(tool_declarations())==9
def test_single_store_false_call():
    class Interactions:
        def __init__(self): self.calls=[]
        def create(self,**kw): self.calls.append(kw); return {"status":"completed","steps":[]}
    class SDK: pass
    sdk=SDK(); sdk.interactions=Interactions(); adapter=GeminiProviderAdapter(sdk)
    req=CommonInteractionRequest("gemini","m","e","prompt","baseline","1","h","r","s","i",[],False)
    adapter.create_once(req); assert len(sdk.interactions.calls)==1; assert sdk.interactions.calls[0]["store"] is False; assert "previous_interaction_id" not in sdk.interactions.calls[0]
