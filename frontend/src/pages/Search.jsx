import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import axios from 'axios'

const API_URL = 'http://localhost:8000'

export default function Search() {
  const [searchParams] = useSearchParams()
  const initialQuery = searchParams.get('q') || ''

  // 기본 상태
  const [source, setSource] = useState('mac')
  const [status, setStatus] = useState({ mac: { count: 0 }, gdrive: { count: 0 } })
  const [loading, setLoading] = useState(false)

  // 대화 상태
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const messagesEndRef = useRef(null)

  // 검색 결과
  const [results, setResults] = useState([])
  
  // 검색 히스토리 (뒤로가기용)
  const [searchHistory, setSearchHistory] = useState([])

  // 선택된 사진 & 추천
  const [selectedImage, setSelectedImage] = useState(null)
  const [recommendations, setRecommendations] = useState(null)
  const [showRecommendPanel, setShowRecommendPanel] = useState(false)

  // 모달 (메인 사진용)
  const [modalImage, setModalImage] = useState(null)
  
  // 추천 사진 모달 (이유 표시용)
  const [recommendModalImage, setRecommendModalImage] = useState(null)
  const [recommendModalReason, setRecommendModalReason] = useState('')

  // 상태 조회
  useEffect(() => {
    fetchStatus()
  }, [])

  // 초기 쿼리 처리
  useEffect(() => {
    if (initialQuery) {
      handleSearch(initialQuery)
    }
  }, [initialQuery])

  // 메시지 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const fetchStatus = async () => {
    try {
      const res = await axios.get(`${API_URL}/status`)
      setStatus(res.data)
      if (res.data.mac.count === 0 && res.data.gdrive.count > 0) {
        setSource('gdrive')
      }
    } catch (err) {
      console.error('상태 조회 실패:', err)
    }
  }

  // 검색 실행
  const handleSearch = async (query) => {
    if (!query.trim()) return

    // 🔥 현재 결과 + 선택된 사진을 히스토리에 저장
    if (results.length > 0) {
      setSearchHistory(prev => [...prev, { 
        results: [...results],
        selectedImage: selectedImage,
        recommendations: recommendations
      }])
    }

    // 새 검색 시 우측 패널 클리어
    setSelectedImage(null)
    setRecommendations(null)
    setShowRecommendPanel(false)

    // 사용자 메시지 추가
    const userMsg = { role: 'user', content: query }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)
    setInputValue('')

    try {
      const res = await axios.post(`${API_URL}/search`, {
        query: query,
        source: source,
        top_k: 20
      })

      // AI 응답 추가
      const aiMsg = { role: 'assistant', content: res.data.response }
      setMessages(prev => [...prev, aiMsg])
      setResults(res.data.results)

    } catch (err) {
      console.error('검색 실패:', err)
      const errorMsg = { role: 'assistant', content: '검색 중 오류가 발생했어요. 다시 시도해주세요.' }
      setMessages(prev => [...prev, errorMsg])
    } finally {
      setLoading(false)
    }
  }

  // 폼 제출
  const handleSubmit = (e) => {
    e.preventDefault()
    handleSearch(inputValue)
  }

  // 메인 사진 클릭 - 추천 패널 열기 + 추천 가져오기
  const handlePhotoClick = async (photo) => {
    setSelectedImage(photo)
    setShowRecommendPanel(true)

    // 추천 가져오기
    try {
      const res = await axios.get(`${API_URL}/recommendations/${photo.id}?source=${source}`)
      setRecommendations(res.data.recommendations)
    } catch (err) {
      console.error('추천 조회 실패:', err)
      setRecommendations(null)
    }
  }

  // 추천 사진 클릭 - 모달 + 이유 표시
  const handleRecommendPhotoClick = (photo, reason) => {
    setRecommendModalImage(photo)
    setRecommendModalReason(reason)
  }

  // 유사 사진 검색 (버튼 클릭)
  const handleFindSimilar = async (imageId, type = 'visual') => {
    // 🔥 현재 결과 + 선택된 사진을 히스토리에 저장
    if (results.length > 0) {
      setSearchHistory(prev => [...prev, { 
        results: [...results],
        selectedImage: selectedImage,
        recommendations: recommendations
      }])
    }

    // 검색 시작 시 우측 패널 클리어
    setSelectedImage(null)
    setRecommendations(null)
    setShowRecommendPanel(false)

    setLoading(true)
    try {
      const res = await axios.post(`${API_URL}/similar?source=${source}`, {
        image_id: imageId,
        similarity_type: type,
        top_k: 20
      })

      setResults(res.data.results)

      const typeDesc = {
        visual: '비슷한 분위기의',
        location: '같은 장소에서 찍은',
        time: '같은 날 찍은'
      }[type]

      const aiMsg = { role: 'assistant', content: `🎨 ${typeDesc} 사진 ${res.data.results.length}장을 찾았어요!` }
      setMessages(prev => [...prev, aiMsg])

    } catch (err) {
      console.error('유사 검색 실패:', err)
    } finally {
      setLoading(false)
    }
  }

  // 소스 변경
  const handleSourceChange = (newSource) => {
    setSource(newSource)
    setResults([])
    setMessages([])
    setSelectedImage(null)
    setRecommendations(null)
    setShowRecommendPanel(false)
  }

  // 대화 초기화
  const handleReset = () => {
    setMessages([])
    setResults([])
    setSelectedImage(null)
    setRecommendations(null)
    setShowRecommendPanel(false)
    setSearchHistory([])
  }

  // 🔥 뒤로가기
  const handleGoBack = async () => {
    if (searchHistory.length === 0) return
    
    const lastSearch = searchHistory[searchHistory.length - 1]
    setResults(lastSearch.results)
    setSearchHistory(prev => prev.slice(0, -1))
    
    // 메시지 추가
    const aiMsg = { role: 'assistant', content: '⬅️ 이전 검색 결과로 돌아왔어요!' }
    setMessages(prev => [...prev, aiMsg])
    
    // 🔥 저장된 선택 사진 복원
    if (lastSearch.selectedImage) {
      setSelectedImage(lastSearch.selectedImage)
      setRecommendations(lastSearch.recommendations)
      setShowRecommendPanel(true)
    } else {
      setSelectedImage(null)
      setRecommendations(null)
      setShowRecommendPanel(false)
    }
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return ''
    try {
      const date = new Date(dateStr)
      return date.toLocaleDateString('ko-KR', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      })
    } catch {
      return dateStr
    }
  }

  // 예시 쿼리
  const exampleQueries = [
    "서울에서 먹은 고기",
    "강아지 사진 보여줘",
    "파리에서 찍은 사진 있어?",
    "Is there a picture of the White House?"
  ]

  return (
    <div className="h-screen flex flex-col bg-gray-100 overflow-hidden">
      {/* 헤더 - 고정 */}
      <header className="bg-white shadow-sm z-40 flex-shrink-0">
        <div className="max-w-full mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-800">
                📸 Picta
              </h1>
              <span className="text-xs bg-gradient-to-r from-purple-500 to-blue-500 text-white px-2 py-0.5 rounded-full">
                AI
              </span>
            </div>

            {/* 소스 선택 */}
            <div className="flex items-center gap-2">
              <div className="flex bg-gray-100 rounded-lg p-1">
                <button
                  onClick={() => handleSourceChange('mac')}
                  className={`px-4 py-2 rounded-md text-sm font-medium transition ${
                    source === 'mac'
                      ? 'bg-white shadow text-gray-800'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  🍎 맥북 ({status.mac.count}장)
                </button>
                <button
                  onClick={() => handleSourceChange('gdrive')}
                  className={`px-4 py-2 rounded-md text-sm font-medium transition ${
                    source === 'gdrive'
                      ? 'bg-white shadow text-gray-800'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  ☁️ 구글 드라이브 ({status.gdrive.count}장)
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* 메인 컨텐츠 - 고정 높이 */}
      <div className="flex-1 flex overflow-hidden">

        {/* 좌측: 대화 패널 - 고정 */}
        <div className="w-80 bg-white border-r border-gray-200 flex flex-col flex-shrink-0">
          {/* 대화 헤더 */}
          <div className="p-4 border-b border-gray-200 flex justify-between items-center flex-shrink-0">
            <h3 className="font-semibold text-gray-700">💬 대화형 검색</h3>
            <button
              onClick={handleReset}
              className="text-gray-400 hover:text-gray-600 text-sm"
              title="대화 초기화"
            >
              🔄
            </button>
          </div>

          {/* 메시지 영역 - 스크롤 */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 ? (
              <div className="text-center py-8">
                <div className="text-5xl mb-4">📷</div>
                <p className="text-gray-600 font-medium mb-2">사진을 검색해보세요!</p>
                <p className="text-gray-400 text-sm mb-4">자연어로 검색할 수 있어요</p>

                <div className="space-y-2">
                  {exampleQueries.map((q, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSearch(q)}
                      className="block w-full text-left px-3 py-2 text-sm bg-gray-50 hover:bg-purple-50 hover:text-purple-600 rounded-lg transition"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[85%] px-4 py-2 rounded-2xl text-sm ${
                        msg.role === 'user'
                          ? 'bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-br-md'
                          : 'bg-gray-100 text-gray-700 rounded-bl-md'
                      }`}
                    >
                      {msg.content}
                    </div>
                  </div>
                ))}

                {loading && (
                  <div className="flex justify-start">
                    <div className="bg-gray-100 px-4 py-2 rounded-2xl rounded-bl-md">
                      <div className="flex gap-1">
                        <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                        <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                        <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* 입력 폼 - 고정 */}
          <form onSubmit={handleSubmit} className="p-4 border-t border-gray-200 flex-shrink-0">
            <div className="flex gap-2">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder="사진을 검색해보세요..."
                className="flex-1 px-4 py-2 border border-gray-300 rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !inputValue.trim()}
                className="w-10 h-10 bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-full flex items-center justify-center hover:opacity-90 disabled:opacity-50 transition"
              >
                🔍
              </button>
            </div>
          </form>
        </div>

        {/* 중앙: 검색 결과 - 스크롤 */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* 🔥 검색했을 때만 헤더 표시 (뒤로가기 + 결과 개수) */}
          {(messages.length > 0 || searchHistory.length > 0) && (
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                {/* 뒤로가기 버튼 - 히스토리 있으면 항상 표시 */}
                {searchHistory.length > 0 && (
                  <button
                    onClick={handleGoBack}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-full transition"
                  >
                    ⬅️ 뒤로
                  </button>
                )}
                <span className="text-sm text-gray-500">📷 {results.length}장의 사진</span>
              </div>
            </div>
          )}

          {results.length > 0 ? (
            <>

              {/* 그리드 - 3열 */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {results.map((result, index) => (
                  <div
                    key={result.id}
                    className={`bg-white rounded-xl shadow-sm overflow-hidden cursor-pointer hover:shadow-lg transition transform hover:-translate-y-1 ${
                      selectedImage?.id === result.id ? 'ring-2 ring-purple-500' : ''
                    }`}
                    onClick={() => handlePhotoClick(result)}
                  >
                    <div className="aspect-[4/3] bg-gray-200 relative group">
                      <img
                        src={`${API_URL}/image/${source}/${result.id}`}
                        alt={`검색 결과 ${index + 1}`}
                        className="w-full h-full object-cover"
                        loading="lazy"
                        onError={(e) => {
                          e.target.parentElement.parentElement.style.display = 'none'
                        }}
                      />
                      <div className="absolute top-3 left-3 bg-black/60 text-white text-sm px-3 py-1 rounded-full">
                        #{index + 1}
                        {result.similarity && (
                          <span className="ml-1 opacity-75">
                            ({(result.similarity * 100).toFixed(0)}%)
                          </span>
                        )}
                      </div>
                      
                      {/* 확대 버튼 */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setModalImage(result)
                        }}
                        className="absolute top-3 right-3 w-10 h-10 bg-white/90 hover:bg-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition shadow-md"
                      >
                        🔍
                      </button>
                    </div>

                    <div className="p-4">
                      <p className="text-base text-gray-700 mb-1">
                        📅 {formatDate(result.taken_date) || '날짜 없음'}
                      </p>
                      <p className="text-sm text-gray-500 truncate">
                        📍 {result.location_name || '위치 없음'}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : loading ? (
            /* 🔥 로딩 중일 때 */
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <div className="flex justify-center gap-2 mb-4">
                  <span className="w-3 h-3 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                  <span className="w-3 h-3 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                  <span className="w-3 h-3 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                </div>
                <p className="text-gray-500">사진을 찾고 있어요...</p>
              </div>
            </div>
          ) : messages.length > 0 ? (
            /* 🔥 검색했는데 결과 0개일 때 */
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <p className="text-5xl mb-4">🔍</p>
                <p className="text-gray-500 text-lg">조건에 맞는 사진이 없어요</p>
                <p className="text-gray-400 text-sm mt-2">다른 키워드로 검색해보세요</p>
              </div>
            </div>
          ) : (
            /* 아직 검색 안했을 때 */
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <p className="text-6xl mb-4">🖼️</p>
                <p className="text-gray-500 text-lg">검색 결과가 여기에 표시됩니다</p>
              </div>
            </div>
          )}
        </div>

        {/* 우측: 사진 정보 + 추천 패널 */}
        {showRecommendPanel && selectedImage && (
          <div className="w-80 bg-white border-l border-gray-200 flex flex-col flex-shrink-0">
            {/* 헤더 */}
            <div className="p-4 border-b border-gray-200 flex justify-between items-center flex-shrink-0">
              <h3 className="font-semibold text-gray-700">📷 사진 정보</h3>
              <button
                onClick={() => {
                  setShowRecommendPanel(false)
                  setSelectedImage(null)
                }}
                className="w-6 h-6 rounded-full bg-gray-100 hover:bg-gray-200 flex items-center justify-center text-gray-500 text-sm"
              >
                ✕
              </button>
            </div>

            {/* 스크롤 영역 */}
            <div className="flex-1 overflow-y-auto">
              {/* 선택된 사진 */}
              <div className="p-4 border-b border-gray-200">
                <img
                  src={`${API_URL}/image/${source}/${selectedImage.id}`}
                  alt="선택된 사진"
                  className="w-full aspect-video object-cover rounded-lg mb-3 cursor-pointer hover:opacity-90 transition"
                  onClick={() => setModalImage(selectedImage)}
                />
                <div className="space-y-1 text-sm">
                  <p className="text-gray-700">
                    📅 {formatDate(selectedImage.taken_date) || '날짜 없음'}
                  </p>
                  <p className="text-gray-500 truncate">
                    📍 {selectedImage.location_name || '위치 없음'}
                  </p>
                </div>
              </div>

              {/* 빠른 검색 버튼 */}
              <div className="p-4 border-b border-gray-200 space-y-2">
                <button
                  onClick={() => handleFindSimilar(selectedImage.id, 'visual')}
                  className="w-full px-4 py-2 text-sm bg-purple-50 hover:bg-purple-100 text-purple-700 rounded-lg transition text-left"
                >
                  🎨 비슷한 분위기 사진
                </button>
                <button
                  onClick={() => handleFindSimilar(selectedImage.id, 'location')}
                  className="w-full px-4 py-2 text-sm bg-green-50 hover:bg-green-100 text-green-700 rounded-lg transition text-left"
                >
                  📍 같은 장소 사진
                </button>
                <button
                  onClick={() => handleFindSimilar(selectedImage.id, 'time')}
                  className="w-full px-4 py-2 text-sm bg-amber-50 hover:bg-amber-100 text-amber-700 rounded-lg transition text-left"
                >
                  📅 같은 날 사진
                </button>
              </div>

              {/* 추천 섹션 */}
              {recommendations && (
                <div className="p-4 space-y-6">
                  {/* 비슷한 분위기 */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 mb-3">🎨 비슷한 분위기</h4>
                    {recommendations.similar_visual?.length > 0 ? (
                      <div className="grid grid-cols-3 gap-2">
                        {recommendations.similar_visual.slice(0, 6).map((photo) => (
                          <div
                            key={photo.id}
                            className="aspect-square rounded-lg overflow-hidden cursor-pointer hover:opacity-80 transition hover:ring-2 hover:ring-purple-400"
                            onClick={() => handleRecommendPhotoClick(photo, '🎨 비슷한 분위기')}
                          >
                            <img
                              src={`${API_URL}/image/${source}/${photo.id}`}
                              alt="추천"
                              className="w-full h-full object-cover"
                              onError={(e) => {
                                e.target.parentElement.style.display = 'none'
                              }}
                            />
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-gray-400">추천 사진이 없습니다</p>
                    )}
                  </div>

                  {/* 같은 장소 */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 mb-3">📍 같은 장소</h4>
                    {recommendations.same_location?.length > 0 ? (
                      <div className="grid grid-cols-3 gap-2">
                        {recommendations.same_location.slice(0, 6).map((photo) => (
                          <div
                            key={photo.id}
                            className="aspect-square rounded-lg overflow-hidden cursor-pointer hover:opacity-80 transition hover:ring-2 hover:ring-green-400"
                            onClick={() => handleRecommendPhotoClick(photo, '📍 같은 장소')}
                          >
                            <img
                              src={`${API_URL}/image/${source}/${photo.id}`}
                              alt="추천"
                              className="w-full h-full object-cover"
                              onError={(e) => {
                                e.target.parentElement.style.display = 'none'
                              }}
                            />
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-gray-400">같은 장소 사진이 없습니다</p>
                    )}
                  </div>

                  {/* 같은 날 */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 mb-3">📅 같은 날</h4>
                    {recommendations.same_day?.length > 0 ? (
                      <div className="grid grid-cols-3 gap-2">
                        {recommendations.same_day.slice(0, 6).map((photo) => (
                          <div
                            key={photo.id}
                            className="aspect-square rounded-lg overflow-hidden cursor-pointer hover:opacity-80 transition hover:ring-2 hover:ring-amber-400"
                            onClick={() => handleRecommendPhotoClick(photo, '📅 같은 날')}
                          >
                            <img
                              src={`${API_URL}/image/${source}/${photo.id}`}
                              alt="추천"
                              className="w-full h-full object-cover"
                              onError={(e) => {
                                e.target.parentElement.style.display = 'none'
                              }}
                            />
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-gray-400">같은 날 사진이 없습니다</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 메인 사진 모달 (버튼 있음) */}
      {modalImage && (
        <div
          className="fixed inset-0 bg-black/90 flex items-center justify-center z-50 p-4"
          onClick={() => setModalImage(null)}
        >
          <button
            className="absolute top-4 right-4 w-12 h-12 bg-white/20 hover:bg-white/30 rounded-full flex items-center justify-center text-white text-2xl transition"
            onClick={() => setModalImage(null)}
          >
            ✕
          </button>
          
          <div
            className="bg-white rounded-2xl max-w-5xl max-h-[90vh] overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <img
              src={`${API_URL}/image/${source}/${modalImage.id}`}
              alt="확대된 이미지"
              className="max-h-[75vh] w-auto mx-auto"
            />
            <div className="p-5 space-y-3">
              <div className="flex flex-wrap gap-4 text-sm">
                <span className="text-gray-700">📅 {formatDate(modalImage.taken_date) || '날짜 없음'}</span>
                <span className="text-gray-500">📍 {modalImage.location_name || '위치 없음'}</span>
                {modalImage.similarity && (
                  <span className="text-gray-400">🎯 유사도: {(modalImage.similarity * 100).toFixed(1)}%</span>
                )}
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => {
                    handleFindSimilar(modalImage.id, 'visual')
                    setModalImage(null)
                  }}
                  className="px-5 py-2.5 text-sm bg-purple-100 hover:bg-purple-200 text-purple-700 rounded-full transition font-medium"
                >
                  🎨 비슷한 사진
                </button>
                <button
                  onClick={() => {
                    handleFindSimilar(modalImage.id, 'location')
                    setModalImage(null)
                  }}
                  className="px-5 py-2.5 text-sm bg-green-100 hover:bg-green-200 text-green-700 rounded-full transition font-medium"
                >
                  📍 같은 장소
                </button>
                <button
                  onClick={() => {
                    handleFindSimilar(modalImage.id, 'time')
                    setModalImage(null)
                  }}
                  className="px-5 py-2.5 text-sm bg-amber-100 hover:bg-amber-200 text-amber-700 rounded-full transition font-medium"
                >
                  📅 같은 날
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 추천 사진 모달 (이유만 표시, 버튼 없음) */}
      {recommendModalImage && (
        <div
          className="fixed inset-0 bg-black/90 flex items-center justify-center z-50 p-4"
          onClick={() => setRecommendModalImage(null)}
        >
          <button
            className="absolute top-4 right-4 w-12 h-12 bg-white/20 hover:bg-white/30 rounded-full flex items-center justify-center text-white text-2xl transition"
            onClick={() => setRecommendModalImage(null)}
          >
            ✕
          </button>
          
          <div
            className="bg-white rounded-2xl max-w-5xl max-h-[90vh] overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <img
              src={`${API_URL}/image/${source}/${recommendModalImage.id}`}
              alt="확대된 이미지"
              className="max-h-[75vh] w-auto mx-auto"
            />
            <div className="p-5 space-y-3">
              <div className="flex flex-wrap gap-4 text-sm">
                <span className="text-gray-700">📅 {formatDate(recommendModalImage.taken_date) || '날짜 없음'}</span>
                <span className="text-gray-500">📍 {recommendModalImage.location_name || '위치 없음'}</span>
              </div>

              {/* 추천 이유 표시 */}
              <div className="pt-2">
                <span className={`inline-block px-4 py-2 rounded-full text-sm font-medium ${
                  recommendModalReason.includes('분위기') ? 'bg-purple-100 text-purple-700' :
                  recommendModalReason.includes('장소') ? 'bg-green-100 text-green-700' :
                  'bg-amber-100 text-amber-700'
                }`}>
                  {recommendModalReason}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
