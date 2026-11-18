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

query = "Làm thế nào để chatbot trả lời theo tài liệu mới nhất?"

documents = [
    "Khi tài liệu thay đổi, cần cập nhật lại kho dữ liệu của chatbot và loại bỏ các phiên bản đã hết hiệu lực.",
    "Chatbot có thể trả lời câu hỏi của người dùng và hỗ trợ tìm kiếm thông tin nhanh chóng.",
    "Để tránh sử dụng thông tin lỗi thời, hãy đồng bộ nội dung mới vào hệ thống tìm kiếm sau mỗi lần chỉnh sửa.",
    "Python là ngôn ngữ lập trình thường được sử dụng để xây dựng ứng dụng trí tuệ nhân tạo.",
    "Nên hiển thị tên tài liệu và ngày cập nhật trong câu trả lời để người dùng kiểm tra nguồn thông tin.",
    "Công ty cần sao lưu tài liệu thường xuyên để có thể khôi phục dữ liệu khi xảy ra sự cố.",
    "Nếu chatbot lưu câu trả lời cũ trong bộ nhớ đệm, cần làm mới bộ nhớ đệm khi tài liệu nguồn thay đổi.",
    "Để chatbot trả lời nhanh hơn, có thể nâng cấp máy chủ hoặc giảm số lượng tài liệu tìm kiếm.",
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
    enumerate(zip(documents, scores.tolist()), start=1),
    key=lambda item: item[1][1],
    reverse=True,
)

print("\n" + "=" * 72)
print("C\u00c2U H\u1eceI:", query)
print("=" * 72)

for rank, (doc_id, (doc, score)) in enumerate(ranked, start=1):
    print(f"\nH\u1ea1ng {rank:02d} | DOC_{doc_id:02d} | \u0110i\u1ec3m: {score:.5f}")
    print("-" * 72)
    print(" ".join(doc.split()))
