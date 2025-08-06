import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  AppBar,
  Toolbar,
  Typography,
  Button,
  Box,
  Menu,
  MenuItem,
  IconButton,
  Breadcrumbs,
  Link,
  Chip,
} from '@mui/material';
import {
  AccountCircle,
  AdminPanelSettings,
  Visibility,
  Home,
  KeyboardArrowDown,
} from '@mui/icons-material';

const Navbar = ({ userRole }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [anchorEl, setAnchorEl] = useState(null);

  const handleMenu = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleNavigation = (path) => {
    navigate(path);
    handleClose();
  };

  // Generate breadcrumbs based on current path
  const generateBreadcrumbs = () => {
    const pathSegments = location.pathname.split('/').filter(Boolean);
    const breadcrumbs = [
      { label: 'Home', path: '/compounds', icon: <Home sx={{ mr: 0.5 }} fontSize="inherit" /> }
    ];

    if (pathSegments.length > 0) {
      // Handle different path structures
      if (pathSegments[0] === 'compounds' && pathSegments.length > 1) {
        const compound = decodeURIComponent(pathSegments[1]);
        breadcrumbs.push({ label: compound, path: `/compounds/${pathSegments[1]}` });

        if (pathSegments[2] === 'studies' && pathSegments.length > 3) {
          const studyId = decodeURIComponent(pathSegments[3]);
          breadcrumbs.push({ 
            label: studyId, 
            path: `/compounds/${pathSegments[1]}/studies/${pathSegments[3]}` 
          });

          if (pathSegments[4] === 'deliverables' && pathSegments.length > 5) {
            const deliverable = decodeURIComponent(pathSegments[5]);
            breadcrumbs.push({ 
              label: deliverable, 
              path: `/compounds/${pathSegments[1]}/studies/${pathSegments[3]}/deliverables/${pathSegments[5]}` 
            });

            if (pathSegments[6] === 'documents') {
              breadcrumbs.push({ 
                label: 'Documents', 
                path: `/compounds/${pathSegments[1]}/studies/${pathSegments[3]}/deliverables/${pathSegments[5]}/documents` 
              });
            }
          }
        }
      } else if (pathSegments[0] === 'documents' && pathSegments.length > 1) {
        breadcrumbs.push({ 
          label: 'Document Viewer', 
          path: `/documents/${pathSegments[1]}` 
        });
      } else if (pathSegments[0] === 'admin') {
        breadcrumbs.push({ label: 'Admin', path: '/admin' });
        if (pathSegments[1] === 'upload') {
          breadcrumbs.push({ label: 'Upload Documents', path: '/admin/upload' });
        } else if (pathSegments[1] === 'manage') {
          breadcrumbs.push({ label: 'Manage Documents', path: '/admin/manage' });
        }
      }
    }

    return breadcrumbs;
  };

  const breadcrumbs = generateBreadcrumbs();

  return (
    <AppBar position="sticky" color="primary">
      <Toolbar>
        {/* Logo and Title */}
        <Box sx={{ display: 'flex', alignItems: 'center', flexGrow: 1 }}>
          <Typography 
            variant="h6" 
            component="div" 
            sx={{ fontWeight: 'bold', mr: 3 }}
          >
            TLF Analyzer
          </Typography>

          {/* Breadcrumbs */}
          <Breadcrumbs 
            aria-label="breadcrumb" 
            sx={{ 
              color: 'rgba(255, 255, 255, 0.7)',
              '& .MuiBreadcrumbs-separator': {
                color: 'rgba(255, 255, 255, 0.5)',
              }
            }}
          >
            {breadcrumbs.map((crumb, index) => {
              const isLast = index === breadcrumbs.length - 1;
              
              if (isLast) {
                return (
                  <Typography 
                    key={crumb.path} 
                    color="white" 
                    sx={{ display: 'flex', alignItems: 'center' }}
                  >
                    {crumb.icon}
                    {crumb.label}
                  </Typography>
                );
              }

              return (
                <Link
                  key={crumb.path}
                  color="inherit"
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    navigate(crumb.path);
                  }}
                  sx={{ 
                    display: 'flex', 
                    alignItems: 'center',
                    textDecoration: 'none',
                    '&:hover': {
                      textDecoration: 'underline',
                    }
                  }}
                >
                  {crumb.icon}
                  {crumb.label}
                </Link>
              );
            })}
          </Breadcrumbs>
        </Box>

        {/* User Role Indicator */}
        <Chip
          icon={userRole === 'admin' ? <AdminPanelSettings /> : <Visibility />}
          label={userRole === 'admin' ? 'Admin' : 'Viewer'}
          variant="outlined"
          size="small"
          sx={{
            color: 'white',
            borderColor: 'rgba(255, 255, 255, 0.5)',
            mr: 2,
          }}
        />

        {/* Navigation Menu */}
        <Button
          color="inherit"
          endIcon={<KeyboardArrowDown />}
          onClick={handleMenu}
          sx={{ textTransform: 'none' }}
        >
          Navigation
        </Button>
        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={handleClose}
          anchorOrigin={{
            vertical: 'bottom',
            horizontal: 'right',
          }}
          transformOrigin={{
            vertical: 'top',
            horizontal: 'right',
          }}
        >
          <MenuItem onClick={() => handleNavigation('/compounds')}>
            <Home sx={{ mr: 1 }} />
            Browse Documents
          </MenuItem>
          
          {userRole === 'admin' && [
            <MenuItem key="admin-dash" onClick={() => handleNavigation('/admin')}>
              <AdminPanelSettings sx={{ mr: 1 }} />
              Admin Dashboard
            </MenuItem>,
            <MenuItem key="admin-upload" onClick={() => handleNavigation('/admin/upload')}>
              Upload Documents
            </MenuItem>,
            <MenuItem key="admin-manage" onClick={() => handleNavigation('/admin/manage')}>
              Manage Documents
            </MenuItem>
          ]}
        </Menu>

        {/* User Icon */}
        <IconButton
          size="large"
          edge="end"
          aria-label="account"
          color="inherit"
          sx={{ ml: 1 }}
        >
          <AccountCircle />
        </IconButton>
      </Toolbar>
    </AppBar>
  );
};

export default Navbar;
