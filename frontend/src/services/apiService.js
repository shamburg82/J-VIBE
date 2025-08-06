import axios from 'axios';

// Determine the base URL based on environment
const getBaseURL = () => {
  // In development, use proxy setup
  if (process.env.NODE_ENV === 'development') {
    return '/api/v1';
  }
  
  // In production (Posit Connect/Workbench), use relative paths
  // The root path will be handled by the FastAPI app's root_path configuration
  return '/api/v1';
};


// Create axios instance with base configuration
const api = axios.create({
  baseURL: getBaseURL(),
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for logging
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error) => {
    console.error('API Request Error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    console.error('API Response Error:', error);
    
    if (error.response) {
      // Server responded with error status
      const message = error.response.data?.detail || error.response.data?.message || 'Server error';
      throw new Error(`${error.response.status}: ${message}`);
    } else if (error.request) {
      // Request was made but no response received
      throw new Error('No response from server. Please check your connection.');
    } else {
      // Something else happened
      throw new Error(error.message || 'Unknown error occurred');
    }
  }
);

export const apiService = {
  // Health check
  async checkHealth() {
    const response = await api.get('/health');
    return response.data;
  },

  // Document structure endpoints
  async getCompounds() {
    const response = await api.get('/documents/compounds');
    return response.data;
  },

  async getStudiesForCompound(compound) {
    const response = await api.get(`/documents/studies/${encodeURIComponent(compound)}`);
    return response.data;
  },

  async getDeliverablesForStudy(compound, studyId) {
    const response = await api.get(
      `/documents/deliverables/${encodeURIComponent(compound)}/${encodeURIComponent(studyId)}`
    );
    return response.data;
  },

  async getDocumentsForDeliverable(compound, studyId, deliverable) {
    const response = await api.get(
      `/documents/documents/${encodeURIComponent(compound)}/${encodeURIComponent(studyId)}/${encodeURIComponent(deliverable)}`
    );
    return response.data;
  },

  // Document endpoints
  async getDocumentInfo(documentId) {
    const response = await api.get(`/documents/info/${documentId}`);
    return response.data;
  },

  async getDocumentsList(params = {}) {
    const response = await api.get('/documents/list', { params });
    return response.data;
  },

  async deleteDocument(documentId) {
    const response = await api.delete(`/documents/${documentId}`);
    return response.data;
  },

  // Document upload
  async uploadDocument(formData, onProgress) {
    const response = await api.post('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          onProgress(percentCompleted);
        }
      },
    });
    return response.data;
  },

  // Processing status
  async getProcessingStatus(documentId) {
    const response = await api.get(`/documents/status/${documentId}`);
    return response.data;
  },

  // Streaming status updates
  createStatusStream(documentId) {
    const baseUrl = getBaseURL().replace('/api/v1', ''); // Remove the API prefix for EventSource
    const eventSource = new EventSource(`${baseUrl}/api/v1/documents/upload-stream/${documentId}`);
    return eventSource;
  },

  // Query endpoints
  async queryDocument(documentId, query, options = {}) {
    const response = await api.post('/queries/ask', {
      document_id: documentId,
      query: query,
      ...options,
    });
    return response.data;
  },

  async getAvailableSources(documentId) {
    const response = await api.get(`/queries/sources/${documentId}`);
    return response.data;
  },

  // Chat endpoints
  async createChatSession(documentId, title = null) {
    const response = await api.post('/chat/new', {
      document_id: documentId,
      title: title,
    });
    return response.data;
  },

  async sendChatMessage(sessionId, message, options = {}) {
    const response = await api.post('/chat/message', {
      session_id: sessionId,
      message: message,
      ...options,
    });
    return response.data;
  },

  async getChatSession(sessionId) {
    const response = await api.get(`/chat/session/${sessionId}`);
    return response.data;
  },

  async getChatSessions(documentId = null) {
    const params = documentId ? { document_id: documentId } : {};
    const response = await api.get('/chat/sessions', { params });
    return response.data;
  },

  async updateChatSession(sessionId, updates) {
    const response = await api.put(`/chat/session/${sessionId}`, updates);
    return response.data;
  },

  async deleteChatSession(sessionId) {
    const response = await api.delete(`/chat/session/${sessionId}`);
    return response.data;
  },

  async clearChatHistory(sessionId, keepSystemMessages = true) {
    const response = await api.post(`/chat/session/${sessionId}/clear`, {
      keep_system_messages: keepSystemMessages,
    });
    return response.data;
  },

  // Streaming chat
  createChatStream(sessionId, message, options = {}) {
    const baseUrl = getBaseURL().replace('/api/v1', ''); // Remove the API prefix for EventSource
    const eventSource = new EventSource(
      `${baseUrl}/api/v1/chat/message-stream?${new URLSearchParams({
        session_id: sessionId,
        message: message,
        ...options,
      }).toString()}`
    );
    return eventSource;
  },

  // Quick start chat with streaming
  createQuickStartChatStream(documentId, message, title = null) {
    const baseUrl = getBaseURL().replace('/api/v1', ''); // Remove the API prefix for EventSource
    const params = new URLSearchParams({
      document_id: documentId,
      first_message: message,
    });
    
    if (title) {
      params.append('title', title);
    }
    
    const eventSource = new EventSource(`${baseUrl}/api/v1/chat/quick-start-stream?${params.toString()}`);
    return eventSource;
  },

  // Check if document is ready for chat
  async checkDocumentChatReady(documentId) {
    const response = await api.get(`/document/${documentId}/chat-ready`);
    return response.data;
  },

  // Get chat examples
  async getChatExamples() {
    const response = await api.get('/chat/examples');
    return response.data;
  },

  // Admin endpoints
  async getDocumentsSummary() {
    const response = await api.get('/documents/summary');
    return response.data;
  },

  async getSystemStats() {
    const response = await api.get('/health/stats');
    return response.data;
  },

  async getDetailedHealth() {
    const response = await api.get('/health/detailed');
    return response.data;
  },
};

// Utility functions for handling streaming responses
export const streamingUtils = {
  // Parse Server-Sent Events data
  parseSSEData(data) {
    try {
      return JSON.parse(data);
    } catch (error) {
      console.warn('Failed to parse SSE data:', data);
      return { error: 'Invalid data format' };
    }
  },

  // Create a promise-based wrapper for EventSource
  createStreamPromise(eventSource, onData, onError) {
    return new Promise((resolve, reject) => {
      const cleanup = () => {
        eventSource.close();
      };

      eventSource.onmessage = (event) => {
        try {
          const data = this.parseSSEData(event.data);
          if (onData) {
            onData(data);
          }
          
          // Check for completion
          if (data.type === 'complete' || data.type === 'error') {
            cleanup();
            if (data.type === 'error') {
              reject(new Error(data.data?.error || 'Stream error'));
            } else {
              resolve(data);
            }
          }
        } catch (error) {
          cleanup();
          if (onError) {
            onError(error);
          }
          reject(error);
        }
      };

      eventSource.onerror = (error) => {
        cleanup();
        if (onError) {
          onError(error);
        }
        reject(new Error('EventSource connection error'));
      };

      // Cleanup on timeout (optional)
      setTimeout(() => {
        if (eventSource.readyState !== EventSource.CLOSED) {
          cleanup();
          reject(new Error('Stream timeout'));
        }
      }, 60000); // 1 minute timeout
    });
  },
};

export default apiService;
