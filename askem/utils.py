import os
import pickle
import secrets
import string
import textwrap

import elasticsearch
import weaviate
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()


def generate_api_key(length=32) -> str:
    characters = string.ascii_letters + string.digits
    api_key = "".join(secrets.choice(characters) for _ in range(length))
    return api_key


def wrap_print(text, width=150) -> None:
    print(textwrap.fill(text, width=width))


def get_text(docid: str) -> str:
    """Get text from ElasticSearch.
    1. Connect to ES
    2. Look up document
    3. Return contents field
    """

    ES_HOST = os.getenv("ES_HOST")
    ES_CERT_PATH = os.getenv("ES_CERT_PATH")
    ES_USER = os.getenv("ES_USER")
    ES_PASSWORD = os.getenv("ES_PASSWORD")

    if not os.path.exists(ES_CERT_PATH):
        raise Exception("No ES certs provided!")

    client = elasticsearch.Elasticsearch(
        hosts=[ES_HOST],
        request_timeout=30,
        verify_certs=True,
        ca_certs=ES_CERT_PATH,
        basic_auth=(ES_USER, ES_PASSWORD),
    )

    article = client.get(id=docid, index="articles")
    contents = article["_source"]["contents"]

    if isinstance(contents, list):
        contents = contents[0]
    return contents


def get_batch_with_cursor(
    client, class_name, class_properties, batch_size, cursor=None
):
    query = (
        client.query.get(class_name, class_properties)
        .with_additional(["id"])
        .with_limit(batch_size)
    )

    if cursor is not None:
        return query.with_after(cursor).do()
    else:
        return query.do()


def count_docs(
    client: weaviate.Client,
    class_name: str = "Passage",
    batch_size: int = 5000,
) -> dict:
    """Count the number of documents in a topic."""

    _tmp = client.query.aggregate(class_name).with_meta_count().do()
    n = _tmp["data"]["Aggregate"][class_name][0]["meta"]["count"]

    paper_ids = {}
    count_paragraphs = {}
    cursor = None

    with tqdm(total=n) as progress_bar:
        while True:
            batch = get_batch_with_cursor(
                client,
                class_name,
                ["topic", "paper_id"],
                batch_size,
                cursor=cursor,
            )

            if len(batch["data"]["Get"][class_name]) == 0:
                break

            objects_list = batch["data"]["Get"][class_name]
            for obj in objects_list:
                # Count paragraphs
                count_paragraphs[obj["topic"]] = (
                    count_paragraphs.get(obj["topic"], 0) + 1
                )

                # Store paper ids as set
                paper_ids[obj["topic"]] = paper_ids.get(obj["topic"], set())
                paper_ids[obj["topic"]].add(obj["paper_id"])

            cursor = batch["data"]["Get"][class_name][-1]["_additional"]["id"]
            progress_bar.update(batch_size)

    counts = {
        "n_paragraphs": count_paragraphs,
        "n_papers": {k: len(v) for k, v in paper_ids.items()},
    }
    with open("document_counts.pkl", "wb") as fout:
        pickle.dump(paper_ids, fout)
    return counts
