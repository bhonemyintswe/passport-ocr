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

export const exportToExcel = async (passports, file, fileHandle) => {
  const fileBuffer = await file.arrayBuffer();

  const formData = new FormData();
  formData.append('excel_file', new File([fileBuffer], file.name, { type: file.type }));
  formData.append('passports_json', JSON.stringify(passports));

  const response = await api.post('/api/export', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    responseType: 'arraybuffer',
  });

  // Try to write back to the same file (File System Access API)
  if (fileHandle) {
    try {
      const writable = await fileHandle.createWritable();
      await writable.write(response.data);
      await writable.close();
      return 'saved';
    } catch {
      // Fall through to download
    }
  }

  // Fallback: download the modified file
  const url = window.URL.createObjectURL(new Blob([response.data], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  }));
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', file.name);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
  return 'downloaded';
};

export default api;
