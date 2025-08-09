import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardActionArea,
  Box,
  Paper,
  Chip,
  LinearProgress,
  Alert,
  Button,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Switch,
  FormControlLabel,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  DialogContentText,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from '@mui/material';
import {
  CloudUpload,
  Settings,
  Assessment,
  Warning,
  CheckCircle,
  Error,
  Description,
  Science,
  Assignment,
  Schedule,
  Storage,
  Folder,
  ExpandMore,
  Info,
  Build,
} from '@mui/icons-material';
import { apiService } from '../../services/apiService';
import { format } from 'date-fns';

const AdminDashboard = () => {
  const navigate = useNavigate();
  const [systemStats, setSystemStats] = useState(null);
  const [healthStatus, setHealthStatus] = useState(null);
  const [documentsSummary, setDocumentsSummary] = useState(null);
  const [vectorStoreConfig, setVectorStoreConfig] = useState(null);
  const [recentDocuments, setRecentDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [configDialog, setConfigDialog] = useState({ open: false, action: null });
  const [configLoading, setConfigLoading] = useState(false);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true);
        
        // Fetch all dashboard data in parallel
        const [stats, health, docSummary, vectorConfig] = await Promise.all([
          apiService.getSystemStats(),
          apiService.getDetailedHealth(),
          apiService.getDocumentsSummary(),
          apiService.getVectorStoreConfig().catch(() => null), // Optional - may not be implemented yet
        ]);

        setSystemStats(stats);
        setHealthStatus(health);
        setDocumentsSummary(docSummary);
        setVectorStoreConfig(vectorConfig);
        setRecentDocuments(docSummary.recent_documents || []);

      } catch (err) {
        setError('Failed to load dashboard data: ' + err.message);
        console.error('Dashboard error:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  const handleVectorStoreToggle = async (enable) => {
    setConfigDialog({ 
      open: true, 
      action: enable ? 'enable' : 'disable',
      title: enable ? 'Enable Vector Store' : 'Disable Vector Store',
      message: enable ? 
        'This will enable full document processing with vector indexing for future uploads. Documents will be searchable and support chat functionality.' :
        'This will disable vector store processing. Future uploads will only store files without indexing. Chat functionality will not be available for new documents.',
      confirmText: enable ? 'Enable' : 'Disable'
    });
  };

  const confirmVectorStoreChange = async () => {
    try {
      setConfigLoading(true);
      
      const endpoint = configDialog.action === 'enable' ? 
        '/api/v1/config/vector-store/enable' : 
        '/api/v1/config/vector-store/disable';
      
      // Make API call to toggle vector store
      const response = await fetch(endpoint, { method: 'POST' });
      if (!response.ok) {
        throw new Error(`Failed to ${configDialog.action} vector store`);
      }
      
      const result = await response.json();
      setVectorStoreConfig({ vector_store_config: result.config });
      
      setConfigDialog({ open: false, action: null });
      
      // Show success message
      setError(null);
      
    } catch (err) {
      setError(`Failed to ${configDialog.action} vector store: ${err.message}`);
    } finally {
      setConfigLoading(false);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'success';
      case 'failed': return 'error';
      case 'processing': return 'warning';
      default: return 'default';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return <CheckCircle color="success" />;
      case 'failed': return <Error color="error" />;
      case 'processing': return <Schedule color="warning" />;
      default: return <Description />;
    }
  };

  const formatUptime = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    
    if (hours > 24) {
      const days = Math.floor(hours / 24);
      return `${days}d ${hours % 24}h`;
    } else if (hours > 0) {
      return `${hours}h ${minutes}m`;
    } else {
      return `${minutes}m`;
    }
  };

  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4 }}>
        <Box sx={{ textAlign: 'center' }}>
          <Typography variant="h6" gutterBottom>
            Loading dashboard...
          </Typography>
          <LinearProgress sx={{ mt: 2 }} />
        </Box>
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4 }}>
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
        <Button onClick={() => window.location.reload()}>
          Retry
        </Button>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Admin Dashboard
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Monitor system health and manage TLF documents
        </Typography>
      </Box>

      {/* Vector Store Configuration Card */}
      {vectorStoreConfig && (
        <Card sx={{ mb: 4 }}>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">
                <Storage sx={{ mr: 1, verticalAlign: 'middle' }} />
                Vector Store Configuration
              </Typography>
              <Chip 
                label={vectorStoreConfig.vector_store_config.enabled ? 'Enabled' : 'Disabled'}
                color={vectorStoreConfig.vector_store_config.enabled ? 'success' : 'warning'}
                variant="outlined"
              />
            </Box>
            
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Vector store controls document indexing and chat functionality. When disabled, 
              only file storage is performed.
            </Typography>

            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h5" color="primary">
                    {vectorStoreConfig.vector_store_config.documents_with_vector_index || 0}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    With Vector Index
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h5" color="warning.main">
                    {vectorStoreConfig.vector_store_config.documents_file_only || 0}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Files Only
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h5">
                    {vectorStoreConfig.vector_store_config.total_documents || 0}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Total Documents
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={vectorStoreConfig.vector_store_config.enabled}
                        onChange={(e) => handleVectorStoreToggle(e.target.checked)}
                        disabled={configLoading}
                      />
                    }
                    label="Enable Vector Store"
                  />
                </Box>
              </Grid>
            </Grid>

            <Accordion>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography variant="body2">
                  <Info sx={{ mr: 1, fontSize: 'small', verticalAlign: 'middle' }} />
                  Advanced Configuration
                </Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <Typography variant="body2" color="text.secondary">
                      Storage Path:
                    </Typography>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                      {vectorStoreConfig.vector_store_config.storage_path}
                    </Typography>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography variant="body2" color="text.secondary">
                      Manifest Path:
                    </Typography>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                      {vectorStoreConfig.vector_store_config.manifest_path}
                    </Typography>
                  </Grid>
                </Grid>
              </AccordionDetails>
            </Accordion>
          </CardContent>
        </Card>
      )}

      {/* Quick Actions */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={4}>
          <Card>
            <CardActionArea onClick={() => navigate('/admin/upload')}>
              <CardContent sx={{ textAlign: 'center', py: 3 }}>
                <CloudUpload color="primary" sx={{ fontSize: 48, mb: 1 }} />
                <Typography variant="h6" gutterBottom>
                  Upload Documents
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Add new TLF documents to the system
                </Typography>
              </CardContent>
            </CardActionArea>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={4}>
          <Card>
            <CardActionArea onClick={() => navigate('/admin/manage')}>
              <CardContent sx={{ textAlign: 'center', py: 3 }}>
                <Settings color="primary" sx={{ fontSize: 48, mb: 1 }} />
                <Typography variant="h6" gutterBottom>
                  Manage Documents
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  View, edit, and delete existing documents
                </Typography>
              </CardContent>
            </CardActionArea>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={4}>
          <Card>
            <CardActionArea onClick={() => navigate('/compounds')}>
              <CardContent sx={{ textAlign: 'center', py: 3 }}>
                <Assessment color="primary" sx={{ fontSize: 48, mb: 1 }} />
                <Typography variant="h6" gutterBottom>
                  Browse Documents
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  View documents as a regular user
                </Typography>
              </CardContent>
            </CardActionArea>
          </Card>
        </Grid>
      </Grid>

      {/* System Status */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        {/* System Health */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              System Health
            </Typography>
            
            {healthStatus && (
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                  <CheckCircle color="success" sx={{ mr: 1 }} />
                  <Typography variant="body1">
                    Status: {healthStatus.status}
                  </Typography>
                </Box>

                {healthStatus.system && (
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      System Resources:
                    </Typography>
                    <Box sx={{ ml: 2 }}>
                      <Typography variant="body2">
                        Memory: {healthStatus.system.memory_usage_percent}% used
                      </Typography>
                      <Typography variant="body2">
                        Disk: {healthStatus.system.disk_usage_percent}% used
                      </Typography>
                      <Typography variant="body2">
                        CPU Cores: {healthStatus.system.cpu_count}
                      </Typography>
                      <Typography variant="body2">
                        Uptime: {formatUptime(healthStatus.system.uptime_seconds)}
                      </Typography>
                    </Box>
                  </Box>
                )}

                {healthStatus.services && (
                  <Box>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      Services:
                    </Typography>
                    <Box sx={{ ml: 2 }}>
                      {Object.entries(healthStatus.services).map(([service, status]) => (
                        <Typography key={service} variant="body2">
                          {service}: {status}
                        </Typography>
                      ))}
                    </Box>
                  </Box>
                )}
              </Box>
            )}
          </Paper>
        </Grid>

        {/* System Statistics */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              System Statistics
            </Typography>
            
            {systemStats && (
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Box sx={{ textAlign: 'center' }}>
                    <Description color="primary" sx={{ fontSize: 32, mb: 1 }} />
                    <Typography variant="h5">
                      {systemStats.total_documents}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Documents
                    </Typography>
                  </Box>
                </Grid>
                
                <Grid item xs={6}>
                  <Box sx={{ textAlign: 'center' }}>
                    <Assignment color="primary" sx={{ fontSize: 32, mb: 1 }} />
                    <Typography variant="h5">
                      {systemStats.total_chunks}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Chunks
                    </Typography>
                  </Box>
                </Grid>
                
                <Grid item xs={6}>
                  <Box sx={{ textAlign: 'center' }}>
                    <Assessment color="primary" sx={{ fontSize: 32, mb: 1 }} />
                    <Typography variant="h5">
                      {systemStats.total_queries}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Queries
                    </Typography>
                  </Box>
                </Grid>
                
                <Grid item xs={6}>
                  <Box sx={{ textAlign: 'center' }}>
                    <Schedule color="primary" sx={{ fontSize: 32, mb: 1 }} />
                    <Typography variant="h5">
                      {Math.round(systemStats.average_processing_time_seconds)}s
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Avg Process Time
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            )}
          </Paper>
        </Grid>
      </Grid>

      {/* Document Summary */}
      <Grid container spacing={3}>
        {/* Document Status Distribution */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Document Status
            </Typography>
            
            {documentsSummary && (
              <Box>
                {Object.entries(documentsSummary.by_status).map(([status, count]) => (
                  <Box key={status} sx={{ mb: 1 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        {getStatusIcon(status)}
                        <Typography variant="body2" sx={{ ml: 1, textTransform: 'capitalize' }}>
                          {status}
                        </Typography>
                      </Box>
                      <Chip 
                        label={count} 
                        size="small" 
                        color={getStatusColor(status)}
                        variant="outlined"
                      />
                    </Box>
                  </Box>
                ))}
                
                <Divider sx={{ my: 2 }} />
                
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography variant="body2">
                    Total TLF Outputs Found:
                  </Typography>
                  <Typography variant="h6" color="primary">
                    {documentsSummary.total_tlf_outputs}
                  </Typography>
                </Box>
              </Box>
            )}
          </Paper>
        </Grid>

        {/* Recent Documents */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Recent Documents
            </Typography>
            
            <List>
              {recentDocuments.slice(0, 5).map((doc, index) => (
                <ListItem 
                  key={doc.document_id} 
                  sx={{ 
                    px: 0,
                    cursor: 'pointer',
                    '&:hover': { bgcolor: 'action.hover' }
                  }}
                  onClick={() => navigate(`/documents/${doc.document_id}`)}
                >
                  <ListItemIcon>
                    {getStatusIcon(doc.status)}
                  </ListItemIcon>
                  <ListItemText
                    primary={doc.filename}
                    secondary={
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          {doc.compound} • {doc.study_id} • {doc.deliverable}
                        </Typography>
                        <br />
                        <Typography variant="caption" color="text.secondary">
                          {format(new Date(doc.created_at), 'MMM dd, yyyy HH:mm')}
                        </Typography>
                      </Box>
                    }
                  />
                  <Box sx={{ textAlign: 'right' }}>
                    <Typography variant="caption" color="text.secondary">
                      {doc.tlf_outputs_found} TLFs
                    </Typography>
                  </Box>
                </ListItem>
              ))}
            </List>
            
            {recentDocuments.length > 5 && (
              <Button 
                fullWidth 
                variant="outlined" 
                onClick={() => navigate('/admin/manage')}
                sx={{ mt: 1 }}
              >
                View All Documents
              </Button>
            )}
          </Paper>
        </Grid>
      </Grid>

      {/* Vector Store Configuration Dialog */}
      <Dialog
        open={configDialog.open}
        onClose={() => !configLoading && setConfigDialog({ open: false, action: null })}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{configDialog.title}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {configDialog.message}
          </DialogContentText>
          {configDialog.action === 'disable' && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              This will not affect existing documents, only future uploads.
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button 
            onClick={() => setConfigDialog({ open: false, action: null })}
            disabled={configLoading}
          >
            Cancel
          </Button>
          <Button 
            onClick={confirmVectorStoreChange}
            variant="contained"
            disabled={configLoading}
            color={configDialog.action === 'enable' ? 'primary' : 'warning'}
          >
            {configLoading ? 'Processing...' : configDialog.confirmText}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default AdminDashboard;
