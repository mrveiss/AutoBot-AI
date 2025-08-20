/**
 * Lazy Loading Directive for Performance Optimization
 * Implements Intersection Observer API for efficient lazy loading
 */

const lazyLoadOptions = {
  // Start loading when element is 50px away from viewport
  rootMargin: '50px',
  // Trigger when 10% of element is visible
  threshold: 0.1
};

const imageObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const img = entry.target;
      const src = img.getAttribute('data-src');

      if (src) {
        // Create a new image to preload
        const imageLoader = new Image();

        imageLoader.onload = () => {
          // Once loaded, update the src and add fade-in effect
          img.src = src;
          img.classList.add('lazy-loaded');
          img.removeAttribute('data-src');
          imageObserver.unobserve(img);
        };

        imageLoader.onerror = () => {
          // Handle error by showing placeholder or error image
          img.classList.add('lazy-error');
          img.alt = 'Image failed to load';
          imageObserver.unobserve(img);
        };

        // Start loading the image
        imageLoader.src = src;
      }
    }
  });
}, lazyLoadOptions);

export const lazyDirective = {
  mounted(el, binding) {
    // Add loading styles
    el.classList.add('lazy-loading');

    // Set placeholder or loading image
    if (binding.value?.placeholder) {
      el.src = binding.value.placeholder;
    } else {
      // Default placeholder - a 1x1 transparent pixel
      el.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="1" height="1"%3E%3C/svg%3E';
    }

    // Store original src in data attribute
    if (binding.value?.src || el.src !== el.getAttribute('src')) {
      el.setAttribute('data-src', binding.value?.src || el.getAttribute('src'));
      el.removeAttribute('src');
    }

    // Start observing
    imageObserver.observe(el);
  },

  unmounted(el) {
    // Clean up observer
    imageObserver.unobserve(el);
  },

  updated(el, binding) {
    // Handle src changes
    if (binding.value?.src && binding.value.src !== el.getAttribute('data-src')) {
      el.setAttribute('data-src', binding.value.src);
      el.classList.remove('lazy-loaded', 'lazy-error');
      el.classList.add('lazy-loading');
      imageObserver.observe(el);
    }
  }
};

// CSS styles (to be included in main CSS)
export const lazyCSSStyles = `
.lazy-loading {
  background: linear-gradient(45deg, #f0f0f0 25%, transparent 25%),
              linear-gradient(-45deg, #f0f0f0 25%, transparent 25%),
              linear-gradient(45deg, transparent 75%, #f0f0f0 75%),
              linear-gradient(-45deg, transparent 75%, #f0f0f0 75%);
  background-size: 20px 20px;
  background-position: 0 0, 0 10px, 10px -10px, -10px 0px;
  animation: lazy-loading 1s linear infinite;
  opacity: 0.7;
  transition: opacity 0.3s ease;
}

.lazy-loaded {
  opacity: 1;
  animation: fadeIn 0.3s ease;
}

.lazy-error {
  background: #f8f8f8;
  border: 1px dashed #ccc;
  opacity: 0.5;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100px;
}

.lazy-error::before {
  content: "Image failed to load";
  color: #666;
  font-size: 12px;
}

@keyframes lazy-loading {
  0% {
    background-position: 0 0, 0 10px, 10px -10px, -10px 0px;
  }
  100% {
    background-position: 20px 20px, 20px 30px, 30px 10px, 10px 20px;
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
`;

export default lazyDirective;
