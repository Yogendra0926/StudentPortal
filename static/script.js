/* =========================================================
   UNIVERSITY PORTAL
   GLOBAL JAVASCRIPT
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {

    /* =====================================================
       1. PAGE FADE-IN
       ===================================================== */

    document.body.classList.add("page-loaded");


    /* =====================================================
       2. AUTO HIDE FLASH ALERTS
       ===================================================== */

    const alerts = document.querySelectorAll(".alert");

    alerts.forEach((alert, index) => {

        setTimeout(() => {

            alert.style.transition =
                "opacity .5s ease, transform .5s ease";

            alert.style.opacity = "0";

            alert.style.transform =
                "translateX(30px)";

            setTimeout(() => {
                alert.remove();
            }, 500);

        }, 5000 + (index * 500));

    });


    /* =====================================================
       3. CARD SCROLL ANIMATION
       ===================================================== */

    const animatedCards = document.querySelectorAll(
        ".webinar-card, .course-card, .assignment-card, .stat-card, .dashboard-card"
    );

    if ("IntersectionObserver" in window) {

        const observer =
            new IntersectionObserver(
                (entries) => {

                    entries.forEach(entry => {

                        if (entry.isIntersecting) {

                            entry.target.style.opacity = "1";

                            entry.target.style.transform =
                                "translateY(0)";

                            observer.unobserve(
                                entry.target
                            );

                        }

                    });

                },
                {
                    threshold: 0.12
                }
            );

        animatedCards.forEach(card => {

            card.style.opacity = "0";

            card.style.transform =
                "translateY(30px)";

            card.style.transition =
                "opacity .6s ease, transform .6s ease";

            observer.observe(card);

        });

    }


    /* =====================================================
       4. ACCORDION
       ===================================================== */

    const accordionHeaders =
        document.querySelectorAll(
            ".accordion-header"
        );

    accordionHeaders.forEach(header => {

        header.addEventListener(
            "click",
            () => {

                const item =
                    header.closest(
                        ".accordion-item"
                    );

                if (!item) return;

                const isActive =
                    item.classList.contains(
                        "active"
                    );

                document
                    .querySelectorAll(
                        ".accordion-item.active"
                    )
                    .forEach(activeItem => {

                        activeItem.classList.remove(
                            "active"
                        );

                    });

                if (!isActive) {

                    item.classList.add(
                        "active"
                    );

                }

            }
        );

    });


    /* =====================================================
       5. BUTTON RIPPLE EFFECT
       ===================================================== */

    const buttons =
        document.querySelectorAll(
            ".btn, .btn-primary, .register, .quiz-btn"
        );

    buttons.forEach(button => {

        button.style.position = "relative";

        button.style.overflow = "hidden";

        button.addEventListener(
            "click",
            function(event) {

                const ripple =
                    document.createElement(
                        "span"
                    );

                const rect =
                    this.getBoundingClientRect();

                const size =
                    Math.max(
                        rect.width,
                        rect.height
                    );

                ripple.style.width =
                    `${size}px`;

                ripple.style.height =
                    `${size}px`;

                ripple.style.position =
                    "absolute";

                ripple.style.left =
                    `${event.clientX - rect.left - size / 2}px`;

                ripple.style.top =
                    `${event.clientY - rect.top - size / 2}px`;

                ripple.style.borderRadius =
                    "50%";

                ripple.style.background =
                    "rgba(255,255,255,.35)";

                ripple.style.pointerEvents =
                    "none";

                ripple.style.transform =
                    "scale(0)";

                ripple.style.transition =
                    "transform .55s ease, opacity .55s ease";

                this.appendChild(ripple);

                requestAnimationFrame(() => {

                    ripple.style.transform =
                        "scale(2.5)";

                    ripple.style.opacity =
                        "0";

                });

                setTimeout(() => {
                    ripple.remove();
                }, 600);

            }
        );

    });


    /* =====================================================
       6. NUMBER COUNTER ANIMATION
       ===================================================== */

    const counters =
        document.querySelectorAll(
            "[data-count]"
        );

    counters.forEach(counter => {

        const target =
            parseInt(
                counter.dataset.count,
                10
            );

        if (isNaN(target)) return;

        let current = 0;

        const increment =
            Math.max(
                1,
                Math.ceil(target / 40)
            );

        const updateCounter = () => {

            current += increment;

            if (current >= target) {

                counter.textContent =
                    target;

                return;

            }

            counter.textContent =
                current;

            requestAnimationFrame(
                updateCounter
            );

        };

        updateCounter();

    });


    /* =====================================================
       7. CONFIRMATION FOR DANGEROUS ACTIONS
       ===================================================== */

    const confirmButtons =
        document.querySelectorAll(
            "[data-confirm]"
        );

    confirmButtons.forEach(button => {

        button.addEventListener(
            "click",
            event => {

                const message =
                    button.dataset.confirm ||
                    "Are you sure you want to continue?";

                if (!confirm(message)) {

                    event.preventDefault();

                }

            }
        );

    });


    /* =====================================================
       8. MOBILE TOUCH FEEDBACK
       ===================================================== */

    const touchCards =
        document.querySelectorAll(
            ".webinar-card, .course-card, .assignment-card"
        );

    touchCards.forEach(card => {

        card.addEventListener(
            "touchstart",
            () => {

                card.style.transform =
                    "scale(.98)";

            },
            { passive: true }
        );

        card.addEventListener(
            "touchend",
            () => {

                card.style.transform =
                    "";

            },
            { passive: true }
        );

    });


    /* =====================================================
       9. CURRENT YEAR
       ===================================================== */

    document
        .querySelectorAll(
            "[data-current-year]"
        )
        .forEach(element => {

            element.textContent =
                new Date().getFullYear();

        });


    /* =====================================================
       10. BACK TO TOP BUTTON
       ===================================================== */

    let topButton =
        document.querySelector(
            ".back-to-top"
        );

    if (topButton) {

        window.addEventListener(
            "scroll",
            () => {

                if (window.scrollY > 400) {

                    topButton.classList.add(
                        "show"
                    );

                } else {

                    topButton.classList.remove(
                        "show"
                    );

                }

            }
        );

        topButton.addEventListener(
            "click",
            () => {

                window.scrollTo({
                    top: 0,
                    behavior: "smooth"
                });

            }
        );

    }


    /* =====================================================
       11. PASSWORD SHOW / HIDE
       ===================================================== */

    const passwordToggles =
        document.querySelectorAll(
            "[data-password-toggle]"
        );

    passwordToggles.forEach(toggle => {

        toggle.addEventListener(
            "click",
            () => {

                const targetId =
                    toggle.dataset.passwordToggle;

                const input =
                    document.getElementById(
                        targetId
                    );

                if (!input) return;

                if (
                    input.type ===
                    "password"
                ) {

                    input.type =
                        "text";

                    toggle.classList.remove(
                        "fa-eye"
                    );

                    toggle.classList.add(
                        "fa-eye-slash"
                    );

                } else {

                    input.type =
                        "password";

                    toggle.classList.remove(
                        "fa-eye-slash"
                    );

                    toggle.classList.add(
                        "fa-eye"
                    );

                }

            }
        );

    });

});