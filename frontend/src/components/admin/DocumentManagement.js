import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Typography,
  Box,
  Button,
  TextField,
  InputAdornment,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Alert,
  Snackbar,
  MenuItem,
  FormControl,
  InputLabel,
  Select,
  Chip,
  Grid,
} from '@mui/material';
import {
  ArrowBack,
  Search,
  Delete,
  Visibility,
  FilterList,
  Clear,
} from '@mui/icons-material';
import { DataGrid } from '@mui/x-data-grid';
import { apiService } from '../../services/apiService';
import { format } from 'date-fns';

const DocumentManagement = () => {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [compoundFilter, setCompoundFilter] = useState('');
  
  // Dialog states
  const [deleteDialog, setDeleteDialog] = useState({ open: false, document: null });
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info' });
  
  // Available filter options
  const [compounds, setCompounds] = useState([]);
  const statusOptions = ['completed', 'processing', 'failed', 'queued'];

  useEffect(() => {
    fetchDocuments();
    fetchFilterOptions();
  }, []);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      const response = await apiService.getDocumentsList({
        limit: 1000, // Get all documents for management
        offset: 0,
        status_filter: statusFilter || undefined,
        compound_filter: compoundFilter || undefined,
      });
      setDocuments(response);
    } catch (err) {
      setError('Failed to load documents: ' + err.message);
      console.error('Error fetching documents:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchFilterOptions = async () => {
    try {
      const compoundsResponse = await apiService.getCompounds();
      setCompounds(compoundsResponse.compounds || []);
    } catch (err) {
      console.warn('Failed to load filter options:', err);
    }
  };

  // Refetch when filters change
  useEffect(() => {
    fetchDocuments();
  }, [statusFilter, compoundFilter]);

  const handleDeleteClick = (document) => {
    setDeleteDialog({ open: true, document });
  };

  const handleDeleteConfirm = async () => {
    const { document } = deleteDialog;
    if (!document) return;

    try {
      await apiService.deleteDocument(document.document_id);
      
      // Remove from local state
      setDocuments(prev => prev.filter(d => d.document_id !== document.document_id));
      
      setSnackbar({
        open: true,
        message: `Document "${document.filename}" deleted successfully`,
        severity: 'success'
      });
    } catch (err) {
      setSnackbar({
        open: true,
        message: `Failed to delete document: ${err.message}`,
        severity: 'error'
      });
    }

    setDeleteDialog({ open: false, document: null });
  };

  const handleViewDocument = (document) => {
    navigate(`/documents/${document.document_id}`);
  };

  const clearFilters = () => {
    setSearchTerm('');
    setStatusFilter('');
    setCompoundFilter('');
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'success';
      case 'failed': return 'error';
      case 'processing': return 'warning';
      default: return 'default';
    }
  };

  // Filter documents based on search term
  const filteredDocuments = documents.filter(doc => {
    const matchesSearch = !searchTerm || 
      doc.filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (doc.description && doc.description.toLowerCase().includes(searchTerm.toLowerCase())) ||
      doc.study_id.toLowerCase().includes(searchTerm.toLowerCase());
    
    return matchesSearch;
  });

  // DataGrid columns
  const columns = [
    {
      field: 'filename',
      headerName: 'Filename',
      flex: 1,
      minWidth: 250,
      renderCell: (params) => (
        <Box>
          <Typography variant="body2" noWrap>
            {params.value}
          </Typography>
          {params.row.description && (
            <Typography variant="caption" color="text.secondary" noWrap>
              {params.row.description}
            </Typography>
          )}
        </Box>
      ),
    },
    {
      field: 'compound',
      headerName: 'Compound',
      width: 120,
      renderCell: (params) => (
        <Chip label={params.value} size="small" color="primary" variant="outlined" />
      ),
    },
    {
      field: 'study_id',
      headerName: 'Study ID',
      width: 140,
    },
    {
      field: 'deliverable',
      headerName: 'Deliverable',
      width: 180,
      renderCell: (params) => (
        <Typography variant="body2" noWrap>
          {params.value}
        </Typography>
      ),
    },
    {
      field: 'status',
      headerName: 'Status',
      width: 120,
      renderCell: (params) => (
        <Chip 
          label={params.value} 
          size="small" 
          color={getStatusColor(params.value)}
          variant="outlined"
        />
      ),
    },
    {
      field: 'tlf_outputs_found',
      headerName: 'TLF Outputs',
      width: 100,
      type: 'number',
      renderCell: (params) => (
        <Typography variant="body2" color="primary" fontWeight="medium">
          {params.value || 0}
        </Typography>
      ),
    },
    {
      field: 'total_pages',
      headerName: 'Pages',
      width: 80,
      type: 'number',
    },
    {
      field: 'created_at',
      headerName: 'Created',
      width: 140,
      renderCell: (params) => (
        <Typography variant="body2">
          {params.value ? format(new Date(params.value), 'MMM dd, yyyy') : 'N/A'}
        </Typography>
      ),
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 120,
      sortable: false,
      renderCell: (params) => (
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            size="small"
            startIcon={<Visibility />}
            onClick={() => handleViewDocument(params.row)}
            disabled={params.row.status !== 'completed'}
          >
            View
          </Button>
          <Button
            size="small"
            color="error"
            startIcon={<Delete />}
            onClick={() => handleDeleteClick(params.row)}
          >
            Delete
          </Button>
        </Box>
      ),
    },
  ];

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Button 
          startIcon={<ArrowBack />} 
          onClick={() => navigate('/admin')}
          sx={{ mb: 2 }}
        >
          Back to Dashboard
        </Button>
        
        <Typography variant="h4" component="h1" gutterBottom>
          Document Management
        </Typography>
        <Typography variant="body1" color="text.secondary">
          View, search, and manage all TLF documents in the system
        </Typography>
      </Box>

      {/* Filters and Controls */}
      <Box sx={{ mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={6} md={4}>
            <TextField
              fullWidth
              variant="outlined"
              placeholder="Search documents..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search />
                  </InputAdornment>
                ),
              }}
            />
          </Grid>
          
          <Grid item xs={12} sm={6} md={2}>
            <FormControl fullWidth>
              <InputLabel>Status</InputLabel>
              <Select
                value={statusFilter}
                label="Status"
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <MenuItem value="">All</MenuItem>
                {statusOptions.map(status => (
                  <MenuItem key={status} value={status}>
                    {status.charAt(0).toUpperCase() + status.slice(1)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} sm={6} md={2}>
            <FormControl fullWidth>
              <InputLabel>Compound</InputLabel>
              <Select
                value={compoundFilter}
                label="Compound"
                onChange={(e) => setCompoundFilter(e.target.value)}
              >
                <MenuItem value="">All</MenuItem>
                {compounds.map(compound => (
                  <MenuItem key={compound} value={compound}>
                    {compound}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} sm={6} md={2}>
            <Button
              fullWidth
              variant="outlined"
              startIcon={<Clear />}
              onClick={clearFilters}
            >
              Clear Filters
            </Button>
          </Grid>

          <Grid item xs={12} sm={6} md={2}>
            <Button
              fullWidth
              variant="contained"
              onClick={() => navigate('/admin/upload')}
            >
              Upload New
            </Button>
          </Grid>
        </Grid>
      </Box>

      {/* Summary Stats */}
      <Box sx={{ mb: 3 }}>
        <Grid container spacing={2}>
          <Grid item>
            <Chip 
              label={`Total: ${filteredDocuments.length}`} 
              color="primary" 
              variant="outlined" 
            />
          </Grid>
          <Grid item>
            <Chip 
              label={`Completed: ${filteredDocuments.filter(d => d.status === 'completed').length}`} 
              color="success" 
              variant="outlined" 
            />
          </Grid>
          <Grid item>
            <Chip 
              label={`Processing: ${filteredDocuments.filter(d => d.status === 'processing').length}`} 
              color="warning" 
              variant="outlined" 
            />
          </Grid>
          <Grid item>
            <Chip 
              label={`Failed: ${filteredDocuments.filter(d => d.status === 'failed').length}`} 
              color="error" 
              variant="outlined" 
            />
          </Grid>
        </Grid>
      </Box>

      {/* Error Alert */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Data Grid */}
      <Box sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={filteredDocuments}
          columns={columns}
          getRowId={(row) => row.document_id}
          loading={loading}
          pageSizeOptions={[25, 50, 100]}
          initialState={{
            pagination: {
              paginationModel: { pageSize: 25 },
            },
            sorting: {
              sortModel: [{ field: 'created_at', sort: 'desc' }],
            },
          }}
          disableRowSelectionOnClick
          sx={{
            '& .MuiDataGrid-row:hover': {
              backgroundColor: 'action.hover',
            },
          }}
        />
      </Box>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={deleteDialog.open}
        onClose={() => setDeleteDialog({ open: false, document: null })}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Confirm Delete</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to delete the document "{deleteDialog.document?.filename}"?
          </DialogContentText>
          <DialogContentText sx={{ mt: 2, color: 'error.main' }}>
            This action cannot be undone. All associated chat sessions and processing data will be lost.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialog({ open: false, document: null })}>
            Cancel
          </Button>
          <Button 
            onClick={handleDeleteConfirm} 
            color="error" 
            variant="contained"
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert 
          severity={snackbar.severity} 
          onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default DocumentManagement;
