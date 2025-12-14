import { BrowserRouter, Routes, Route } from "react-router-dom"
import Home from "./pages/Home"
import Search from "./pages/Search"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>

        {/* 홈 화면 (yeri modified)*/}
        <Route path="/" element={<Home />} />

        {/* 검색 화면 (jiyeon modified)*/} 
        <Route path="/search" element={<Search />} />

      </Routes>
    </BrowserRouter>
  )
}