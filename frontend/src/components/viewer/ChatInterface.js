import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  TextField,
  IconButton,
  Paper,
  Typography,
  List,
  ListItem,
  Avatar,
  Chip,
  Link,
  CircularProgress,
  Alert,
  Divider,
  Button,
  Menu,
  MenuItem,
  Tooltip,
} from '@mui/material';
import {
  Send,
  Person,
  SmartToy,
  MoreVert,
  Clear,
  Refresh,
  ContentCopy,
  Share,
} from '@mui/icons-material';
import { apiService, streamingUtils } from '../../services/apiService';

const ChatInterface = ({ 
  documentId, 
  onSourceClick, 
  chatSession, 
  setChatSession 
}) => {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [error, setError] = useState(null);
  const [chatExamples, setChatExamples] = useState(null);
  const [menuAnchor, setMenuAnchor] = useState(null);
  
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const streamingRef = useRef(null);

  // Auto-scroll to bottom when new messages are added
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent]);

  // Load chat examples on mount
  useEffect(() => {
    const loadExamples = async () => {
      try {
        const examples = await apiService.getChatExamples();
        setChatExamples(examples);
      } catch (err) {
        console.warn('Failed to load chat examples:', err);
      }
    };

    loadExamples();
  }, []);

  // Initialize chat session
  useEffect(() => {
    const initializeChat = async () => {
      if (!documentId || chatSession) return;

      try {
        const newSession = await apiService.createChatSession(
          documentId,
          'Document Chat'
        );
        setChatSession(newSession);
        setMessages(newSession.messages || []);
      } catch (err) {
        setError('Failed to initialize chat: ' + err.message);
        console.error('Chat initialization error:', err);
      }
    };

    initializeChat();
  }, [documentId, chatSession, setChatSession]);

  const handleSendMessage = async (messageText = null) => {
    const message = messageText || inputValue.trim();
    if (!message || isStreaming || !chatSession) return;

    // Clear input and add user message
    setInputValue('');
    const userMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: message,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setIsStreaming(true);
    setStreamingContent('');
    setError(null);

    try {
        // Start streaming response
        const baseUrl = window.location.pathname.includes('/p/') 
          ? window.location.pathname.split('/p/')[0] + '/p/' + window.location.pathname.split('/p/')[1].split('/')[0]
          : '';
        
        const eventSource = new EventSource(
          `${baseUrl}/api/v1/chat/message-stream?session_id=${chatSession.id}&message=${encodeURIComponent(message)}&include_context=true`
        );

      let assistantMessage = {
        id: Date.now().toString() + '_assistant',
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        sources: [],
        processing_time_ms: 0,
      };

      streamingRef.current = eventSource;

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          switch (data.type) {
            case 'content':
              setStreamingContent(prev => prev + data.data);
              assistantMessage.content += data.data;
              break;
              
            case 'sources':
              assistantMessage.sources = data.data || [];
              break;
              
            case 'complete':
              setMessages(prev => [...prev, assistantMessage]);
              setStreamingContent('');
              setIsStreaming(false);
              eventSource.close();
              streamingRef.current = null;
              break;
              
            case 'error':
              throw new Error(data.data?.error || 'Chat error');
              
            default:
              console.log('Unknown stream event:', data);
          }
        } catch (parseError) {
          console.error('Failed to parse stream data:', parseError);
        }
      };

      eventSource.onerror = (error) => {
        console.error('EventSource error:', error);
        setError('Connection error. Please try again.');
        setIsStreaming(false);
        setStreamingContent('');
        eventSource.close();
        streamingRef.current = null;
      };

    } catch (err) {
      setError('Failed to send message: ' + err.message);
      setIsStreaming(false);
      setStreamingContent('');
      console.error('Send message error:', err);
    }
  };

  const handleStopStreaming = () => {
    if (streamingRef.current) {
      streamingRef.current.close();
      streamingRef.current = null;
    }
    setIsStreaming(false);
    setStreamingContent('');
  };

  const handleClearChat = async () => {
    if (!chatSession) return;

    try {
      await apiService.clearChatHistory(chatSession.id, true);
      setMessages([]);
      setError(null);
      setMenuAnchor(null);
    } catch (err) {
      setError('Failed to clear chat: ' + err.message);
    }
  };

  const handleCopyMessage = (content) => {
    navigator.clipboard.writeText(content);
  };

  const handleExampleClick = (example) => {
    setInputValue(example);
    inputRef.current?.focus();
  };

  const handleSourceClick = useCallback((source) => {
    if (onSourceClick && source.page_number) {
      onSourceClick(source.page_number, source.title);
    }
  }, [onSourceClick]);

  const renderMessage = (message, index) => {
    const isUser = message.role === 'user';
    const isAssistant = message.role === 'assistant';

    return (
      <ListItem
        key={message.id || index}
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: isUser ? 'flex-end' : 'flex-start',
          py: 1,
        }}
      >
        <Box
          sx={{
            display: 'flex',
            flexDirection: isUser ? 'row-reverse' : 'row',
            alignItems: 'flex-start',
            gap: 1,
            maxWidth: '85%',
          }}
        >
          <Avatar
            sx={{
              width: 32,
              height: 32,
              bgcolor: isUser ? 'primary.main' : 'secondary.main',
            }}
          >
            {isUser ? <Person fontSize="small" /> : <SmartToy fontSize="small" />}
          </Avatar>

          <Paper
            elevation={1}
            sx={{
              p: 2,
              bgcolor: isUser ? 'primary.light' : 'background.paper',
              color: isUser ? 'primary.contrastText' : 'text.primary',
              borderRadius: 2,
              maxWidth: '100%',
            }}
          >
            <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
              {message.content}
            </Typography>

            {/* Sources for assistant messages */}
            {isAssistant && message.sources && message.sources.length > 0 && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="caption" color="text.secondary" gutterBottom>
                  Sources:
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {message.sources.map((source, idx) => (
                    <Chip
                      key={idx}
                      label={`${source.output_type || 'Output'} ${source.output_number || idx + 1}`}
                      size="small"
                      variant="outlined"
                      clickable
                      onClick={() => handleSourceClick(source)}
                      sx={{
                        fontSize: '0.7rem',
                        height: 24,
                        '&:hover': {
                          bgcolor: 'action.hover',
                        },
                      }}
                    />
                  ))}
                </Box>
              </Box>
            )}

            {/* Message actions */}
            <Box sx={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center',
              mt: 1,
            }}>
              <Typography variant="caption" color="text.secondary">
                {new Date(message.timestamp).toLocaleTimeString()}
              </Typography>
              
              <IconButton
                size="small"
                onClick={() => handleCopyMessage(message.content)}
                sx={{ ml: 1 }}
              >
                <ContentCopy fontSize="small" />
              </IconButton>
            </Box>
          </Paper>
        </Box>
      </ListItem>
    );
  };

  const renderStreamingMessage = () => {
    if (!isStreaming && !streamingContent) return null;

    return (
      <ListItem
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-start',
          py: 1,
        }}
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 1,
            maxWidth: '85%',
          }}
        >
          <Avatar
            sx={{
              width: 32,
              height: 32,
              bgcolor: 'secondary.main',
            }}
          >
            <SmartToy fontSize="small" />
          </Avatar>

          <Paper
            elevation={1}
            sx={{
              p: 2,
              bgcolor: 'background.paper',
              borderRadius: 2,
              maxWidth: '100%',
              position: 'relative',
            }}
          >
            <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
              {streamingContent}
              {isStreaming && (
                <Box component="span" sx={{ ml: 0.5 }}>
                  <CircularProgress size={12} />
                </Box>
              )}
            </Typography>

            {isStreaming && (
              <Button
                size="small"
                onClick={handleStopStreaming}
                sx={{ mt: 1 }}
              >
                Stop
              </Button>
            )}
          </Paper>
        </Box>
      </ListItem>
    );
  };

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Chat Messages */}
      <Box sx={{ flexGrow: 1, overflow: 'auto', p: 1 }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
            <Button onClick={() => setError(null)} sx={{ ml: 1 }}>
              Dismiss
            </Button>
          </Alert>
        )}

        {/* Welcome message with examples */}
        {messages.length === 0 && !isStreaming && (
          <Box sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h6" gutterBottom>
              Chat with your document
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Ask questions about the clinical trial data, tables, and results
            </Typography>

            {chatExamples && (
              <Box sx={{ mt: 3 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Try asking:
                </Typography>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mt: 1 }}>
                  {chatExamples.examples.demographics?.slice(0, 2).map((example, idx) => (
                    <Chip
                      key={idx}
                      label={example}
                      variant="outlined"
                      clickable
                      onClick={() => handleExampleClick(example)}
                      sx={{ alignSelf: 'flex-start' }}
                    />
                  ))}
                  {chatExamples.examples.safety?.slice(0, 1).map((example, idx) => (
                    <Chip
                      key={`safety-${idx}`}
                      label={example}
                      variant="outlined"
                      clickable
                      onClick={() => handleExampleClick(example)}
                      sx={{ alignSelf: 'flex-start' }}
                    />
                  ))}
                </Box>
              </Box>
            )}
          </Box>
        )}

        {/* Message List */}
        <List sx={{ pb: 0 }}>
          {messages.map((message, index) => renderMessage(message, index))}
          {renderStreamingMessage()}
        </List>
        
        <div ref={messagesEndRef} />
      </Box>

      {/* Chat Input */}
      <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider' }}>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
          <TextField
            ref={inputRef}
            fullWidth
            multiline
            maxRows={4}
            placeholder="Ask about the clinical trial data..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            disabled={isStreaming}
            variant="outlined"
            size="small"
          />
          
          <IconButton
            color="primary"
            onClick={() => handleSendMessage()}
            disabled={!inputValue.trim() || isStreaming}
            sx={{ mb: 0.5 }}
          >
            <Send />
          </IconButton>

          <IconButton
            onClick={(e) => setMenuAnchor(e.currentTarget)}
            sx={{ mb: 0.5 }}
          >
            <MoreVert />
          </IconButton>
        </Box>

        {/* Chat Actions Menu */}
        <Menu
          anchorEl={menuAnchor}
          open={Boolean(menuAnchor)}
          onClose={() => setMenuAnchor(null)}
        >
          <MenuItem onClick={handleClearChat}>
            <Clear sx={{ mr: 1 }} />
            Clear Chat
          </MenuItem>
          <MenuItem onClick={() => window.location.reload()}>
            <Refresh sx={{ mr: 1 }} />
            Refresh
          </MenuItem>
        </Menu>

        {/* Tips */}
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          Press Enter to send, Shift+Enter for new line
        </Typography>
      </Box>
    </Box>
  );
};

export default ChatInterface;
