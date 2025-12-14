import { useState } from "react";

export default function SearchBar({ onSearch }) {
  const [query, setQuery] = useState("");

  return (
    <div className="flex w-full border border-uiGray rounded-xl overflow-hidden shadow-sm focus-within:ring-2 ring-brand transition">
      <input
        type="text"
        placeholder="예: 파스타 먹는 사진 찾아줘"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="flex-1 px-6 py-4 text-lg focus:outline-none"
      />
      <button
        onClick={() => onSearch(query)}
        className="bg-brand text-white px-10 text-lg hover:opacity-90 transition"
      >
        검색
      </button>
    </div>
  );
}
