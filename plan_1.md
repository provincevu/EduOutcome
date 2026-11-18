# Kế hoạch MVP EduOutcome — quy mô nhỏ, triển khai 6–8 tuần

## 1. Phạm vi MVP đã thu gọn

Ứng dụng phục vụ khoảng 50 giảng viên, tối đa 5 người dùng đồng thời. Mục tiêu là làm đúng luồng đánh giá cốt lõi, không xây dựng hạ tầng phức tạp để mở rộng lớn ngay từ đầu.

- Đăng nhập bằng tài khoản/mật khẩu được quản trị khoa cấp; không tích hợp SSO.
- Quản trị khoa quản lý tài khoản, môn học, CĐR, rubric và tài liệu chính thức.
- Giảng viên tải lên hai tệp Excel `.xlsx`:
  - **Tệp câu hỏi:** mã câu, nội dung câu hỏi, điểm tối đa.
  - **Tệp điểm:** mỗi dòng là một bài làm ẩn danh; các cột điểm theo mã câu và các thông tin bài thi đã được định nghĩa trước.
- Không lưu bất kỳ thông tin định danh sinh viên nào. Mỗi dòng chỉ dùng `submission_ref`/số thứ tự ẩn danh để đối chiếu trong cùng một lần phân tích.
- AI nội bộ đề xuất một CĐR cho mỗi câu hỏi; giảng viên phải duyệt hoặc sửa trước khi chốt.
- Hệ thống tính mức đạt theo rubric cố định do khoa cấu hình, hiển thị dashboard và xuất Excel.
- Chatbot trả lời từ PDF/Word chính thức, luôn dẫn nguồn; không đủ căn cứ thì từ chối trả lời.
- Không làm trong MVP: SSO, tích hợp LMS/SIS, PDF xuất báo cáo, ứng dụng di động, API công khai, nhiều khoa/ngành, nhiều–nhiều giữa câu hỏi và CĐR, hay dashboard quản trị cấp trường.

## 2. Kiến trúc và công nghệ đề xuất

Dùng ứng dụng nguyên khối để giảm thời gian phát triển và vận hành:

| Thành phần | Công nghệ đề xuất |
|---|---|
| Ứng dụng web | Django + Python, giao diện server-rendered với HTMX/Bootstrap |
| Cơ sở dữ liệu | PostgreSQL |
| Nhập/xuất Excel | `openpyxl` và `xlsxwriter` |
| Biểu đồ | Chart.js |
| Trích xuất tài liệu | PyMuPDF cho PDF, `python-docx` cho Word |
| Tìm kiếm tài liệu | PostgreSQL + pgvector |
| AI nội bộ | Ollama chạy trên GPU sẵn có; mô hình được chọn sau benchmark tiếng Việt |
| Tác vụ nền | RQ + Redis cho lập chỉ mục tài liệu và xử lý tệp dài |
| Triển khai | Docker Compose trên một máy chủ nội bộ, Nginx và TLS |

Kiến trúc chỉ gồm các container: `web`, `worker`, `postgres`, `redis`, `ollama` và kho tệp nội bộ. Không dùng microservice, Kubernetes hoặc hạ tầng đám mây trong MVP.

## 3. Nghiệp vụ, dữ liệu và module chính

### Quản trị tài khoản và học thuật

- Vai trò **Quản trị khoa**: tạo/vô hiệu hóa tài khoản, đặt lại mật khẩu, quản lý môn học, CĐR, rubric và tài liệu.
- Vai trò **Giảng viên**: tạo và xem các đợt phân tích của chính mình; không xem dữ liệu của giảng viên khác.
- Rubric được cấu hình cố định theo từng CĐR: mức đánh giá, ngưỡng điểm và mục tiêu tỷ lệ đạt của lớp.

### Nhập và phân tích đợt thi

- Mỗi đợt phân tích thuộc một môn học, một giảng viên và một phiên bản CĐR/rubric.
- Tệp câu hỏi bắt buộc các cột: `question_code`, `question_text`, `max_score`.
- Tệp điểm bắt buộc có các cột điểm trùng mã câu; chỉ chấp nhận thêm các trường metadata đã được quản trị viên định nghĩa, nhằm ngăn vô tình tải lên họ tên, mã số sinh viên hoặc thông tin cá nhân.
- Hệ thống kiểm tra định dạng, cột thiếu/thừa, mã câu không khớp, giá trị không phải số, điểm âm và điểm vượt điểm tối đa.
- Mỗi câu được AI gợi ý đúng một CĐR, kèm lý do và độ tin cậy. Giảng viên xác nhận trước khi chạy phân tích.
- Điểm CĐR của mỗi bài làm ẩn danh là trung bình có trọng số của các câu đã gán vào CĐR đó, sau khi chuẩn hóa theo điểm tối đa.
- Kết quả gồm: phân bố điểm, tỷ lệ đạt theo CĐR, số bài ở từng mức rubric, CĐR chưa đạt mục tiêu, câu hỏi có điểm thấp bất thường và gợi ý cải thiện dựa trên số liệu.

### Chatbot tài liệu

- Quản trị khoa tải PDF/Word, xem trước phần văn bản trích xuất và xuất bản tài liệu.
- Hệ thống chia đoạn, lập chỉ mục ngữ nghĩa và lưu số trang/đoạn nguồn.
- Chatbot chỉ dùng tài liệu đã xuất bản; câu trả lời phải hiển thị nguồn trích dẫn.
- Nếu không tìm được đoạn nguồn đủ phù hợp, chatbot trả lời rằng tài liệu hiện có không đủ căn cứ.

### Các bảng dữ liệu chính

- `users`, `roles`, `courses`, `learning_outcomes`, `rubrics`, `rubric_levels`
- `policy_documents`, `document_chunks`
- `assessment_runs`, `exam_questions`, `question_outcome_mappings`
- `anonymous_submissions`, `question_scores`, `outcome_results`, `analysis_snapshots`
- `chat_sessions`, `chat_messages`, `audit_events`

Thiết kế ánh xạ hiện tại giới hạn một câu hỏi–một CĐR, nhưng dữ liệu vẫn có thể mở rộng thêm trọng số/nhiều CĐR ở giai đoạn sau.

## 4. API và giao diện

MVP không cần API công khai. Django cung cấp các endpoint nội bộ cho giao diện và một số JSON endpoint phục vụ tải tệp, biểu đồ và chatbot.

Các màn hình cần có:

- Đăng nhập, đổi mật khẩu lần đầu.
- Dashboard giảng viên: danh sách các đợt phân tích của chính mình.
- Tạo đợt đánh giá: tải tệp câu hỏi, tải tệp điểm, xem lỗi, xác nhận dữ liệu.
- Duyệt gợi ý câu hỏi–CĐR.
- Dashboard kết quả: tổng quan lớp, kết quả theo CĐR, theo câu hỏi, bảng bài làm ẩn danh và khuyến nghị.
- Xuất Excel.
- Chatbot tài liệu có danh sách trích dẫn.
- Trang quản trị khoa: tài khoản, môn học, CĐR, rubric, tài liệu và nhật ký thao tác.

## 5. Bảo mật và vận hành tối giản

- Mật khẩu được băm bằng Argon2; quản trị viên cấp mật khẩu tạm, giảng viên đổi mật khẩu khi đăng nhập lần đầu.
- Phân quyền ở mọi truy vấn: giảng viên chỉ truy cập đợt do mình tạo.
- Bắt buộc HTTPS, cookie phiên bảo mật, giới hạn số lần đăng nhập sai và ghi audit cho thao tác quản trị/tải tệp/xuất kết quả.
- Giới hạn kích thước và loại tệp `.xlsx`, `.pdf`, `.docx`; quét tệp theo khả năng hạ tầng.
- Dữ liệu không định danh sinh viên; tệp gốc có thể tự xóa sau khi đã nhập thành công theo thời hạn ngắn đã cấu hình.
- Sao lưu PostgreSQL và kho tệp hằng ngày; kiểm tra khôi phục trước pilot.
- AI chạy trên GPU nội bộ, không gửi tài liệu hay dữ liệu bài thi sang dịch vụ bên ngoài.

## 6. Lộ trình 6–8 tuần

1. **Tuần 1 — Chuẩn bị và xác thực khả thi**  
   Chốt 1–3 môn pilot, mẫu hai tệp Excel, CĐR/rubric chính thức, danh sách tài liệu và benchmark GPU/mô hình AI tiếng Việt.

2. **Tuần 2 — Nền tảng ứng dụng**  
   Thiết lập Django, PostgreSQL, Docker, tài khoản/phân quyền, quản trị môn học, CĐR và rubric.

3. **Tuần 3 — Nhập dữ liệu và máy tính đánh giá**  
   Tạo hai mẫu Excel, kiểm tra dữ liệu, lưu bài làm ẩn danh, tính điểm CĐR và xuất Excel cơ bản.

4. **Tuần 4 — Gán câu hỏi–CĐR và dashboard**  
   Tích hợp mô hình AI nội bộ, màn hình giảng viên duyệt ánh xạ, biểu đồ và nhận định dựa trên quy tắc.

5. **Tuần 5 — Tài liệu và chatbot**  
   Tải/trích xuất PDF–Word, lập chỉ mục, trả lời có dẫn nguồn và cơ chế từ chối khi thiếu căn cứ.

6. **Tuần 6 — Kiểm thử và UAT**  
   Kiểm thử đầy đủ luồng, phân quyền, dữ liệu lỗi, dữ liệu ẩn danh và hiệu năng với 5 người dùng đồng thời.

7. **Tuần 7–8 — Pilot và sửa lỗi**  
   Chạy thử với giảng viên thực tế, hiệu chỉnh mẫu Excel, rubric, prompt và trải nghiệm sử dụng.

## 7. Kiểm thử và tiêu chí nghiệm thu

- Tệp Excel sai cấu trúc hoặc điểm không hợp lệ phải được báo lỗi chính xác theo dòng/cột.
- Tệp có cột không được phép phải bị từ chối hoặc yêu cầu quản trị viên duyệt, để tránh tải nhầm dữ liệu cá nhân.
- Kết quả tính điểm phải khớp các bộ Excel mẫu do khoa tính thủ công.
- Giảng viên không thể mở, tải hoặc sửa bất kỳ đợt phân tích nào của người khác.
- 100% câu trả lời chatbot hiển thị nguồn; câu không có nguồn phải từ chối trả lời.
- AI không được tự chốt ánh xạ; luôn cần xác nhận của giảng viên.
- Dashboard và xuất Excel hoàn tất ổn định với quy mô lớp pilot.
- Hệ thống vận hành được với 5 phiên đồng thời trên máy chủ và GPU đã chọn.

## 8. Câu hỏi/điểm cần xác nhận ở tuần đầu để giữ ngân sách thời gian

- GPU có bao nhiêu VRAM, hệ điều hành gì và có quyền cài Docker/Ollama không?
- Môn nào sẽ được chọn pilot, có bao nhiêu CĐR và bao nhiêu tài liệu chính thức?
- Hai mẫu Excel có thể được chuẩn hóa cố định hay mỗi giảng viên đang dùng cấu trúc khác nhau?
- Những metadata bài thi nào được phép xuất hiện trong tệp điểm ngoài các cột điểm?
- Rubric hiện có có quy tắc rõ khi nhiều câu hỏi cùng đo một CĐR hay không?
- Quản trị khoa nào chịu trách nhiệm duyệt CĐR, rubric và tài liệu trước khi đưa vào chatbot?

**Giả định mặc định:** một máy chủ nội bộ có GPU; tài liệu PDF/Word có văn bản; 1–3 môn pilot; Excel `.xlsx` theo mẫu cố định; dữ liệu bài thi hoàn toàn ẩn danh; dashboard và Excel là đầu ra duy nhất của MVP.
