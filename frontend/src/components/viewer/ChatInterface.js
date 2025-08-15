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
  Card,
  CardContent,
  Collapse,
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
  ExpandMore,
  ExpandLess,
  Launch,
  FindInPage,
  Bookmark,
} from '@mui/icons-material';
import { apiService, streamingUtils } from '../../services/apiService';

const ChatInterface = ({ 
  documentId, 
  onSourceClick, 
  onSearchInDocument,
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
  const [expandedSources, setExpandedSources] = useState(new Set());
  
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
    console.log('Chat source clicked:', source);
    if (onSourceClick && source.page_number) {
      // Pass individual parameters as expected by the PDF viewer
      onSourceClick(source.page_number, source.title);
    } else {
      console.warn('No page number found in source:', source);
    }
  }, [onSourceClick]);

  const handleSearchInPdf = useCallback((searchText) => {
    if (onSearchInDocument && searchText) {
      onSearchInDocument(searchText);
    }
  }, [onSearchInDocument]);

  const toggleSourceExpansion = (messageId) => {
    setExpandedSources(prev => {
      const newSet = new Set(prev);
      if (newSet.has(messageId)) {
        newSet.delete(messageId);
      } else {
        newSet.add(messageId);
      }
      return newSet;
    });
  };

  const formatSourceTitle = (source) => {
    const type = source.output_type || 'Output';
    const number = source.output_number || 'Unknown';
    return `${type} ${number}`;
  };

  const extractSearchableTerms = (content) => {
    // Extract potential search terms from the response
    const terms = [];
    
    // Look for table/figure references like "Table 14.3.1", "Figure 1", etc.
    const tableRefs = content.match(/(?:Table|Figure|Listing)\s+[\d.]+/gi);
    if (tableRefs) {
      terms.push(...tableRefs);
    }
    
    // Look for quoted terms that might be searchable
    const quotedTerms = content.match(/"([^"]+)"/g);
    if (quotedTerms) {
      terms.push(...quotedTerms.map(term => term.replace(/"/g, '')));
    }
    
    // Look for medical/clinical terms (simple heuristic)
    const clinicalTerms = content.match(/\b(?:adverse events?|endpoint|efficacy|safety|demographics|baseline|treatment|placebo|dose|mg|patients?|subjects?)\b/gi);
    if (clinicalTerms) {
      terms.push(...new Set(clinicalTerms)); // Remove duplicates
    }
    
    return terms.slice(0, 5); // Limit to 5 terms
  };

  const renderMessage = (message, index) => {
    const isUser = message.role === 'user';
    const isAssistant = message.role === 'assistant';
    const isSourcesExpanded = expandedSources.has(message.id);

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
            width: '100%',
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

          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Paper
              elevation={1}
              sx={{
                p: 2,
                bgcolor: isUser ? 'primary.light' : 'background.paper',
                color: isUser ? 'primary.contrastText' : 'text.primary',
                borderRadius: 2,
                mb: 1,
              }}
            >
              <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
                {message.content}
              </Typography>

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
                
                <Box sx={{ display: 'flex', gap: 0.5 }}>
                  <IconButton
                    size="small"
                    onClick={() => handleCopyMessage(message.content)}
                  >
                    <ContentCopy fontSize="small" />
                  </IconButton>
                  
                  {/* Search in PDF button for assistant messages */}
                  {isAssistant && onSearchInDocument && (
                    <Tooltip title="Search key terms in PDF">
                      <IconButton
                        size="small"
                        onClick={() => {
                          const terms = extractSearchableTerms(message.content);
                          if (terms.length > 0) {
                            handleSearchInPdf(terms[0]); // Search first term
                          }
                        }}
                      >
                        <FindInPage fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                </Box>
              </Box>
            </Paper>

            {/* Enhanced Sources Section */}
            {isAssistant && message.sources && message.sources.length > 0 && (
              <Card variant="outlined" sx={{ mt: 1 }}>
                <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <Typography variant="subtitle2" color="text.secondary" sx={{ flexGrow: 1 }}>
                      Sources ({message.sources.length})
                    </Typography>
                    <IconButton
                      size="small"
                      onClick={() => toggleSourceExpansion(message.id)}
                    >
                      {isSourcesExpanded ? <ExpandLess /> : <ExpandMore />}
                    </IconButton>
                  </Box>

                  {/* Compact source chips */}
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1 }}>
                    {message.sources.slice(0, isSourcesExpanded ? undefined : 3).map((source, idx) => (
                      <Chip
                        key={idx}
                        label={formatSourceTitle(source)}
                        size="small"
                        variant="outlined"
                        clickable
                        onClick={() => handleSourceClick(source)}
                        icon={<Launch />}
                        sx={{
                          fontSize: '0.7rem',
                          height: 24,
                          '&:hover': {
                            bgcolor: 'primary.light',
                            color: 'primary.contrastText',
                          },
                          cursor: 'pointer',
                        }}
                      />
                    ))}
                    {!isSourcesExpanded && message.sources.length > 3 && (
                      <Chip
                        label={`+${message.sources.length - 3} more`}
                        size="small"
                        variant="outlined"
                        onClick={() => toggleSourceExpansion(message.id)}
                        sx={{ fontSize: '0.7rem', height: 24 }}
                      />
                    )}
                  </Box>

                  {/* Expanded source details */}
                  <Collapse in={isSourcesExpanded}>
                    <Divider sx={{ mb: 1 }} />
                    {message.sources.map((source, idx) => (
                      <Box
                        key={idx}
                        sx={{
                          p: 1,
                          mb: 1,
                          bgcolor: 'grey.50',
                          borderRadius: 1,
                          border: 1,
                          borderColor: 'grey.200',
                          '&:hover': {
                            bgcolor: 'grey.100',
                            cursor: 'pointer',
                          },
                        }}
                        onClick={() => {
                          console.log('Source box clicked:', source);
                          handleSourceClick(source);
                        }}
                      >
                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <Box>
                            <Typography variant="body2" fontWeight="medium">
                              {formatSourceTitle(source)}
                            </Typography>
                            {source.title && (
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                {source.title}
                              </Typography>
                            )}
                          </Box>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                            {source.page_number && (
                              <Chip
                                label={`Page ${source.page_number}`}
                                size="small"
                                color="primary"
                                variant="filled"
                                sx={{ fontSize: '0.6rem', height: 20 }}
                              />
                            )}
                            {source.confidence && (
                              <Chip
                                label={`${Math.round(source.confidence * 100)}%`}
                                size="small"
                                color={source.confidence > 0.8 ? 'success' : source.confidence > 0.6 ? 'warning' : 'default'}
                                variant="outlined"
                                sx={{ fontSize: '0.6rem', height: 20 }}
                              />
                            )}
                            <Launch fontSize="small" color="action" />
                          </Box>
                        </Box>
                        
                        {source.chunk_count && source.chunk_count > 1 && (
                          <Typography variant="caption" color="text.secondary">
                            {source.chunk_count} chunks referenced
                          </Typography>
                        )}
                      </Box>
                    ))}
                  </Collapse>

                  {/* Quick search suggestions from this response */}
                  {isSourcesExpanded && (
                    <Box sx={{ mt: 1 }}>
                      <Typography variant="caption" color="text.secondary" gutterBottom>
                        Quick search in PDF:
                      </Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                        {extractSearchableTerms(message.content).slice(0, 3).map((term, idx) => (
                          <Button
                            key={idx}
                            size="small"
                            variant="outlined"
                            startIcon={<FindInPage />}
                            onClick={() => handleSearchInPdf(term)}
                            sx={{ 
                              fontSize: '0.65rem', 
                              height: 22,
                              minWidth: 'auto',
                              px: 1,
                            }}
                          >
                            {term.length > 15 ? `${term.substring(0, 15)}...` : term}
                          </Button>
                        ))}
                      </Box>
                    </Box>
                  )}
                </CardContent>
              </Card>
            )}
          </Box>
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
            <Typography variant="caption" color="text.secondary" gutterBottom>
              💡 Click on sources to navigate to specific pages in the PDF
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
          Press Enter to send, Shift+Enter for new line • Click sources to navigate PDF
        </Typography>
      </Box>
    </Box>
  );
};

export default ChatInterface;
