


from google import genai

# Khởi tạo client (sẽ tự động đọc biến môi trường GEMINI_API_KEY bạn vừa thiết lập)
client = genai.Client()

# Sử dụng đúng phương thức generate_content thuộc namespace models
response = client.models.generate_content(
    model="gemini-3.6-flash", # Hoặc gemini-2.5-pro tùy nhu cầu
    contents="giải thích cách hoạt động của API"
)

print(response.text)
