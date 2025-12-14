import { useNavigate } from "react-router-dom";

export default function PhotoCard({ data }) {
  const navigate = useNavigate();

  return (
    <div
      onClick={() => navigate(`/detail/${data.id}`, { state: data })}
      className="rounded-xl overflow-hidden shadow hover:scale-105 transition cursor-pointer"
    >
      <img src={data.url} className="w-full h-48 object-cover" />
      <div className="p-3">
        <p className="font-semibold">{data.label}</p>
        <p className="text-sm text-gray-500">{data.date}</p>
      </div>
    </div>
  );
}
