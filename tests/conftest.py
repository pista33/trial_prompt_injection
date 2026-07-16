import socket
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/"src"))
@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args,**kwargs): raise AssertionError("network denied")
    monkeypatch.setattr(socket,"socket",denied)
