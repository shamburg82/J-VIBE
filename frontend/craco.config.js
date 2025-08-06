// craco.config.js - Custom Create React App Configuration
module.exports = {
    webpack: {
      configure: (webpackConfig, { env, paths }) => {
        // Set public path to relative for all environments
        if (env === 'production') {
          webpackConfig.output.publicPath = './';
        }
        
        // Ensure chunks use relative paths
        if (webpackConfig.optimization && webpackConfig.optimization.splitChunks) {
          webpackConfig.optimization.splitChunks.cacheGroups = {
            ...webpackConfig.optimization.splitChunks.cacheGroups,
            default: {
              ...webpackConfig.optimization.splitChunks.cacheGroups.default,
              filename: 'static/js/[name].[contenthash:8].chunk.js',
            },
          };
        }
        
        return webpackConfig;
      },
    },
  };
