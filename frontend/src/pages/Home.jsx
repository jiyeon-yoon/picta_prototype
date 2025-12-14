import PhoneMockup from "../components/PhoneMockup";
import ChatBubble from "../components/ChatBubble";
import SearchBar from "../components/SearchBar";
import { useNavigate } from "react-router-dom";

export default function Home() {
  const navigate = useNavigate();

  const handleSearch = (query) => {
    if (!query.trim()) return;
    navigate(`/search?q=${query}`);
  };

  return (
    <div className="min-h-screen flex flex-col items-center bg-black text-white">

      <main className="w-full h-screen overflow-hidden flex justify-center items-center relative">


        {/* ----------------------------- */}
        {/* 📌 1) 핸드폰 + 내부 UI + 말풍선 묶음 */}
        {/* ----------------------------- */}
        <div
          className="
            absolute 
            top-1/2 left-1/2
            -translate-x-[75%] -translate-y-[36%]
          "
        >
          <div className="relative w-fit h-fit">

            {/* 📱 폰 mockup */}
            <PhoneMockup videoSrc="/data/sample_video1.mp4" />

            {/* ⚙ 설정 아이콘 */}
            <div
              className="
                absolute flex items-center justify-center
                bg-white/80 text-black 
                rounded-full shadow-lg cursor-pointer
              "
              style={{
                top: "120px",
                left: "355px",
                width: "26px",
                height: "26px"
              }}
            >
              <div className="text-lg font-bold leading-none relative" style={{ top: "-4px" }}>
                …
              </div>
            </div>

            {/* ♡ / 연세해변 / 날짜 */}
            <div
              className="absolute text-white"
              style={{
                top: "110px",
                left: "320px"
              }}
            >
              <div className="text-4xl leading-tight">♡</div>
              <div className="text-6xl font-bold leading-tight">연세해변</div>
              <div className="text-xl opacity-100 leading-tight">2024년 7월 21일</div>
            </div>


            {/* ----------------------------- */}
            {/* 💬 왼쪽 사용자 말풍선 2개       */}
            {/* ----------------------------- */}
            <div
              className="
                absolute 
                top-[380px]
                left-[30px]
                flex flex-col gap-4
                w-[350px]
              "
              style={{
                fontFamily: "KoPub"
              }}
            >
              <ChatBubble text="지난 해에 갔던 바다 그립다 .. ㅜ ㅜ" delay={0} type="user"/>
              <ChatBubble text="바다 사진 보여줘!" delay={2} type="user"/>
            </div>

            {/* ----------------------------- */}
            {/* 💬 오른쪽 Picta 말풍선 1개      */}
            {/* ----------------------------- */}
            <div
              className="
                absolute
                top-[550px]
                right-[50px]
                w-[350px]
                flex whitespace-nowrap
              "
              style={{
                fontFamily: "KoPub"
              }}
            >
              <ChatBubble text="픽타가 당신의 사진을 분석 중입니다 📸" delay={4} type="manager"/>
            </div>

          </div>
        </div>


        {/* ----------------------------- */}
        {/* 📌 2) 오른쪽 Picta 문구 */}
        {/* ----------------------------- */}
        <div
          className="absolute text-white text-center"
          style={{
            top: "50%",
            left: "60%",
            transform: "translateY(-50%)",
            fontFamily: "KoPub"
          }}
        >
          <div className="text-2xl opacity-90">당신만의 똑똑한 사진 비서</div>
          <div className="text-9xl font-bold leading-tight mb-8">Picta</div>
          
          {/* 버튼: 이 박스 안에서 위치 고정 */}
          <button
            onClick={() => navigate("/search")}
            className="
              px-4 py-1 rounded-full text-2xl
              bg-white text-black hover:bg-blue-500 hover:text-white
              transition-all duration-300 shadow-lg
            "
          >
            시작하기
          </button>
        </div>

      </main>
    </div>
  );
}
