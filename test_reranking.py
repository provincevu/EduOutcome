import torch
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification
)

model_name = "AITeamVN/Vietnamese_Reranker"

tokenizer = AutoTokenizer.from_pretrained(model_name)

model = AutoModelForSequenceClassification.from_pretrained(
    model_name
)
model.eval()

query = "RAG là gì?"

documents = [
    "RAG kết hợp truy xuất tài liệu và LLM.",
    "Python là một ngôn ngữ lập trình.",
    "RAG giúp mô hình AI trả lời dựa trên dữ liệu bên ngoài."
]

pairs = [[query, doc] for doc in documents]

inputs = tokenizer(
    pairs,
    padding=True,
    truncation=True,
    max_length=2304,
    return_tensors="pt"
)

with torch.inference_mode():
    scores = model(**inputs).logits.view(-1).float()

ranked = sorted(
    zip(documents, scores.tolist()),
    key=lambda x: x[1],
    reverse=True
)

for doc, score in ranked:
    print(round(score, 5), doc)
