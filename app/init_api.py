from fastapi import APIRouter
from app import v1
import pkgutil

router = APIRouter(prefix="/api/v1")

def init_endpoints() -> None:
    v1_endpoints = v1.__path__
    endpoint_info = pkgutil.walk_packages(v1_endpoints, f"{v1.__name__}.")

    for _, name, _ in endpoint_info:
        __import__(name)

init_endpoints()