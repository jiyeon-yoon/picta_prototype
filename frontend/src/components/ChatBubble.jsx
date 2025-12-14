import { useEffect, useState } from "react";

export default function ChatBubble({ text, delay = 0, typing = false, type = "user" }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), delay * 1000);
    return () => clearTimeout(timer);
  }, [delay]);

  if (!visible) return null;

  const isUser = type === "user";   // 파란 말풍선
  const isManager = type === "manager";       // 흰 말풍선

  return (
    <div
      className={
        "flex w-full " +
        (isUser ? "justify-end pr-4" : "justify-start pl-4") +
        " animate-chatAppear"
      }
    >
      <div
        className={
          `
          relative px-5 py-2 rounded-2xl max-w-[340px] text-lg shadow-xl
          flex items-center whitespace-nowrap
          ` +
          (isUser ? " bg-blue-500 text-white" : " bg-white text-black")
        }
      >
        {typing ? (
          <span>
            {text}
            <span className="typing-dots"></span>
          </span>
        ) : (
          text
        )}

        {/* 꼬리 */}
        {isUser && (
          <div className="absolute right-[16px] bottom-[-18px] text-blue-500 text-2xl leading-none">
            ▼
          </div>
        )}

        {isManager && (
          <div className="absolute left-[16px] bottom-[-18px] text-white text-2xl leading-none">
            ▼
          </div>
        )}
      </div>
    </div>
  );
}
