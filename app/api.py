from fastapi import APIRouter
from app import endpoints
import pkgutil

router = APIRouter(prefix="/api")


def init_endpoints() -> None:
    v1_endpoints = endpoints.__path__
    endpoint_info = pkgutil.walk_packages(v1_endpoints, f"{endpoints.__name__}.")

    for _, name, _ in endpoint_info:
        __import__(name)


init_endpoints()
