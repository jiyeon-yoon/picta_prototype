export default function PhoneMockup({ videoSrc }) {
  return (
    <div className="relative w-[1000px]">
      {/* 스마트폰 이미지 */}
      <img
        src="/data/phone_frame.png"
        className="w-full pointer-events-none select-none"
        alt="Phone Frame"
      />

      {/* 영상 영역 (비율-조절 버전) */}
      <div
        className="absolute overflow-hidden rounded-[100px]"
        style={{
          top: "0%",        
          left: "23.2%",
          width: "99%",
          height: "100%",
        }}
      >
        <video
          src={videoSrc}
          autoPlay
          muted
          loop
          playsInline
          className="
            absolute 
            top-[4%] left-[6%] 
            h-[100%] w-[45%]  /* ⬅ 여기서 w/h 바꿈 */
            object-cover 
            rounded-[66px]
          "
          style={{ transformOrigin: "center" }}
        />
      </div>
    </div>
  );
}
