import axios from 'axios'

const api = axios.create({
  // Production: Render backend URL
  // Local dev:  set VITE_API_URL=http://localhost:8000 in frontend/.env
  baseURL: import.meta.env.VITE_API_URL || 'https://deploy-breathesafe-backend.onrender.com',
  timeout: 30000,   // 30 s — handles Render cold-start latency
  headers: { 'Content-Type': 'application/json' },
})

// Attach access token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── Token refresh on 401 ──────────────────────────────────────────────────────
// When a request fails with 401:
//   1. Try to get a new access token using the stored refresh token.
//   2. If refresh succeeds → update localStorage + retry the original request.
//   3. If refresh fails (expired/missing) → clear everything and redirect to /login.
let _refreshing = false
let _queue = []   // requests that arrived while a refresh was in-flight

const processQueue = (error, token = null) => {
  _queue.forEach(({ resolve, reject }) =>
    error ? reject(error) : resolve(token)
  )
  _queue = []
}

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config

    // Only intercept 401s that haven't already been retried
    if (err.response?.status !== 401 || original._retry) {
      return Promise.reject(err)
    }

    // Don't intercept the refresh call itself — that would loop forever
    if (original.url?.includes('/auth/refresh')) {
      localStorage.clear()
      window.location.href = '/login'
      return Promise.reject(err)
    }

    if (_refreshing) {
      // Another refresh is already in-flight — queue this request
      return new Promise((resolve, reject) => {
        _queue.push({ resolve, reject })
      }).then((token) => {
        original.headers.Authorization = `Bearer ${token}`
        return api(original)
      })
    }

    original._retry = true
    _refreshing = true

    const refreshToken = localStorage.getItem('refresh_token')
    if (!refreshToken) {
      // No refresh token stored — user was never logged in properly
      localStorage.clear()
      window.location.href = '/login'
      return Promise.reject(err)
    }

    try {
      const { data } = await api.post('/auth/refresh', { refresh_token: refreshToken })
      const newToken = data.access_token

      localStorage.setItem('access_token', newToken)
      localStorage.setItem('refresh_token', data.refresh_token)
      localStorage.setItem('user', JSON.stringify(data.user))
      api.defaults.headers.common['Authorization'] = `Bearer ${newToken}`

      processQueue(null, newToken)
      original.headers.Authorization = `Bearer ${newToken}`
      return api(original)
    } catch (refreshErr) {
      processQueue(refreshErr, null)
      localStorage.clear()
      window.location.href = '/login'
      return Promise.reject(refreshErr)
    } finally {
      _refreshing = false
    }
  }
)

export default api
