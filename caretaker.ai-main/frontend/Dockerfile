FROM nginx:alpine

# Copy static frontend files to Nginx default html directory
COPY . /usr/share/nginx/html

# Expose standard web port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
