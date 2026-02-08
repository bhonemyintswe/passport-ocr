import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || '';

const api = axios.create({
  baseURL: API_URL,
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.reload();
    }
    return Promise.reject(error);
  }
);

export const login = async (username, password) => {
  const response = await api.post('/api/login', { username, password });
  const { access_token } = response.data;
  localStorage.setItem('token', access_token);
  return access_token;
};

export const logout = () => {
  localStorage.removeItem('token');
};

export const isAuthenticated = () => {
  return !!localStorage.getItem('token');
};

export const processPassports = async (files) => {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append('files', file);
  });

  const response = await api.post('/api/ocr', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const exportToExcel = async (passports, fileHandle) => {
  // Read file content into memory immediately to avoid stale state errors
  const file = await fileHandle.getFile();
  const fileBuffer = await file.arrayBuffer();

  const formData = new FormData();
  formData.append('excel_file', new File([fileBuffer], file.name, { type: file.type }));
  formData.append('passports_json', JSON.stringify(passports));

  const response = await api.post('/api/export', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    responseType: 'arraybuffer',
  });

  // Write the modified file back to the same file on disk
  const writable = await fileHandle.createWritable();
  await writable.write(response.data);
  await writable.close();
};

export default api;
