document.addEventListener('DOMContentLoaded', () => {
    /* ==========================================
       1. Parallax Background Circle Effect
       ========================================== */
    const circles = document.querySelectorAll('.bg-circle');
    
    document.addEventListener('mousemove', (e) => {
        const x = e.clientX / window.innerWidth;
        const y = e.clientY / window.innerHeight;
        
        circles.forEach((circle, index) => {
            // Give each circle a slightly different movement multiplier
            const speed = (index + 1) * 20;
            const moveX = (x - 0.5) * speed;
            const moveY = (y - 0.5) * speed;
            
            circle.style.transform = `translate(${moveX}px, ${moveY}px)`;
        });
    });

    /* ==========================================
       2. Input Field Focus & Icon Animation
       ========================================== */
    const inputs = document.querySelectorAll('.input-field input');
    
    inputs.forEach(input => {
        // Highlight icon on focus
        input.addEventListener('focus', () => {
            const icon = input.parentElement.querySelector('i');
            if (icon) {
                icon.style.transform = 'scale(1.15)';
                icon.style.color = '#3b82f6';
            }
        });

        // Revert icon on blur
        input.addEventListener('blur', () => {
            const icon = input.parentElement.querySelector('i');
            if (icon) {
                icon.style.transform = 'scale(1)';
                // Revert color if input is empty
                if (!input.value) {
                    icon.style.color = '#64748b';
                }
            }
        });

        // Retain active color if field contains text
        input.addEventListener('input', () => {
            const icon = input.parentElement.querySelector('i');
            if (icon) {
                icon.style.color = input.value.trim() !== '' ? '#60a5fa' : '#3b82f6';
            }
        });
    });

    /* ==========================================
       3. Smooth Button Loading state on Submit
       ========================================== */
    const form = document.querySelector('form');
    const loginBtn = document.querySelector('.login-btn');
    
    if (form && loginBtn) {
        form.addEventListener('submit', () => {
            const btnSpan = loginBtn.querySelector('span');
            const btnIcon = loginBtn.querySelector('i');
            
            // Replace text and replace arrow with spinning loader
            if (btnSpan) btnSpan.textContent = 'Signing In...';
            if (btnIcon) {
                btnIcon.className = 'fa-solid fa-spinner fa-spin';
            }
            
            loginBtn.style.opacity = '0.85';
            loginBtn.style.pointerEvents = 'none'; // Prevent double submission
        });
    }

    /* ==========================================
       4. Auto-Dismiss Flash Alerts
       ========================================== */
    const alerts = document.querySelectorAll('.alert');
    
    if (alerts.length > 0) {
        setTimeout(() => {
            alerts.forEach(alert => {
                alert.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                alert.style.opacity = '0';
                alert.style.transform = 'translateY(-10px)';
                
                // Remove from DOM after fade out finishes
                setTimeout(() => alert.remove(), 500);
            });
        }, 4500); // Dissolves after 4.5 seconds
    }
});