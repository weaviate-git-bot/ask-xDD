import json
import logging

from auth import has_valid_api_key
from data_models import BaseQuery, Document, HybridQuery, ReactQuery
from engine import ReactManager, hybrid_search, react_search, vector_search
from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse

logging.basicConfig(level=logging.DEBUG)

app = FastAPI(
    title="xdd-llm-prototype",
    description="API for the xdd-llm-prototype.",
    version="0.3.1",
)


@app.get("/")
async def get_root():
    """Health check."""
    return {"ping": "pong!"}


@app.post("/vector", dependencies=[Depends(has_valid_api_key)])
async def get_docs_from_vector(query: BaseQuery) -> list[Document]:
    """Search relevant documents using vector search."""

    logging.debug(f"Accessing vector route with: {query}")
    return vector_search(**query.dict(exclude_none=True))


@app.post("/hybrid", dependencies=[Depends(has_valid_api_key)])
async def hybrid_get_docs(query: HybridQuery) -> list[Document]:
    """Hybrid search relevant documents."""

    logging.debug(f"Accessing hybrid route with: {query}")
    return hybrid_search(**query.dict(exclude_none=True))


@app.post("/react", dependencies=[Depends(has_valid_api_key)])
def react_chain(query: ReactQuery) -> dict:
    """ReAct search chain."""

    logging.debug(f"Accessing react route with: {query}")
    return react_search(**query.dict(exclude_none=True))


@app.post("/react_streaming", dependencies=[Depends(has_valid_api_key)])
async def react_chain(query: ReactQuery) -> dict:
    """ReAct search chain."""

    logging.debug(f"Accessing react streaming route with: {query}")

    search_config = query.dict(exclude_none=True)
    entry_query = search_config.pop("question")
    openai_model_name = search_config.pop("openai_model_name")
    chain = ReactManager(
        entry_query=entry_query,
        openai_model_name=openai_model_name,
        search_config=search_config,
    )
    step_iterator = chain.get_iterator()

    def _formatted_iterator():
        for step in step_iterator:
            if "output" in step:
                messages = [{"answer": step["output"]}]

            elif "intermediate_step" in step:
                action_logs = step["intermediate_step"][0][0].log.split("\n")
                messages = [{"thoughts": log} for log in action_logs if log]

                # Append used documents
                serialized_docs = [
                    doc.dict(exclude_none=True) for doc in chain.latest_used_docs
                ]
                messages.append({"used_docs": serialized_docs})
            else:
                raise ValueError(f"Unknown step: {step}")

            for message in messages:
                yield json.dumps(message) + "\n"

    return StreamingResponse(_formatted_iterator(), media_type="application/json")
