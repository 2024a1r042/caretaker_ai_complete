// Toggle specialization and care recipients based on role
const roleSelect = document.getElementById('role');
const specializationGroup = document.getElementById('specializationGroup');
const careRecipientsContainer = document.getElementById('careRecipientsContainer');
const registerTitle = document.getElementById('registerTitle');

function updateUIForRole(role) {
    if (role === 'doctor') {
        registerTitle.innerText = 'Register as Doctor';
        specializationGroup.style.display = 'block';
        careRecipientsContainer.style.display = 'none';
        const loginLink = document.querySelector('.form-footer a');
        if (loginLink) loginLink.href = 'login.html?role=doctor';
        document.querySelectorAll('.care-recipient input, .care-recipient select').forEach(el => {
            el.removeAttribute('required');
        });
    } else {
        registerTitle.innerText = 'Register as CareTaker';
        specializationGroup.style.display = 'none';
        careRecipientsContainer.style.display = 'block';
        const loginLink = document.querySelector('.form-footer a');
        if (loginLink) loginLink.href = 'login.html?role=caretaker';
        document.querySelectorAll('[name="recipient_name"], [name="recipient_age"], [name="recipient_gender"], [name="recipient_condition"]').forEach(el => {
            el.setAttribute('required', '');
        });
    }
}

// Check for role in URL
const urlParams = new URLSearchParams(window.location.search);
const initialRole = urlParams.get('role');
if (initialRole) {
    roleSelect.value = initialRole;
    updateUIForRole(initialRole);
}

roleSelect.addEventListener('change', () => {
    updateUIForRole(roleSelect.value);
});

document.getElementById('registerForm').addEventListener('submit', async (e) => {
    alert('Registering... Please wait.');
    e.preventDefault();

    try {
        const role = document.getElementById('role').value;
        const specialization = document.getElementById('specialization').value;

        // Get main details
        const formData = {
            full_name: document.getElementById('full_name').value,
            email: document.getElementById('email').value,
            username: document.getElementById('username').value,
            phone_number: document.getElementById('phone_number').value,
            password: document.getElementById('password').value,
            role: role,
            specialization: role === 'doctor' ? specialization : null,
            care_recipients: []
        };

        // Validate main details
        if (!formData.full_name || !formData.email || !formData.username || !formData.phone_number || !formData.password) {
            throw new Error('Please fill out all the main registration fields.');
        }

        if (role === 'caretaker') {
            const recipientDivs = document.querySelectorAll('.care-recipient');
            let validationError = null;
            recipientDivs.forEach(div => {
                if (validationError) return;

                const nameVal = div.querySelector('[name="recipient_name"]').value;
                const ageVal = div.querySelector('[name="recipient_age"]').value;
                const genderVal = div.querySelector('[name="recipient_gender"]').value;
                const conditionVal = div.querySelector('[name="recipient_condition"]').value;

                if (!nameVal || !ageVal || !genderVal || !conditionVal) {
                    validationError = 'Please fill out required recipient fields (Name, Age, Gender, Condition)';
                    return;
                }

                const heightVal = div.querySelector('[name="recipient_height"]').value;
                const weightVal = div.querySelector('[name="recipient_weight"]').value;

                const recipient = {
                    full_name: nameVal,
                    email: div.querySelector('[name="recipient_email"]').value || null,
                    phone_number: div.querySelector('[name="recipient_phone"]').value || null,
                    age: parseInt(ageVal),
                    gender: genderVal,
                    respiratory_condition_status: conditionVal === 'true',
                    height: heightVal ? parseFloat(heightVal) : null,
                    weight: weightVal ? parseFloat(weightVal) : null,
                    blood_group: div.querySelector('[name="recipient_blood_group"]').value || null,
                    emergency_contact: div.querySelector('[name="recipient_emergency_contact"]').value || null
                };

                formData.care_recipients.push(recipient);
            });

            if (validationError) throw new Error(validationError);
            if (formData.care_recipients.length === 0) throw new Error('At least one care recipient is required for caretakers.');
        }

        console.log('Sending registration data:', formData);
        const API_BASE = 'http://127.0.0.1:8000';
        const response = await fetch(API_BASE + '/api/signup', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });

        const responseData = await response.json();
        if (!response.ok) {
            throw new Error(responseData.detail || 'Registration failed.');
        }

        const token = responseData.result && responseData.result.access_token;
        if (token) localStorage.setItem('token', token);

        if (role === 'caretaker') {
            const createdRecipients = responseData.result && responseData.result.care_recipients ? responseData.result.care_recipients : [];
            const recipientDivsAfter = document.querySelectorAll('.care-recipient');

            for (let i = 0; i < recipientDivsAfter.length && i < createdRecipients.length; i++) {
                const div = recipientDivsAfter[i];
                const fileInput = div.querySelector('[name="recipient_report"]');

                if (fileInput && fileInput.files && fileInput.files.length > 0) {
                    const file = fileInput.files[0];
                    const uploadData = new FormData();
                    uploadData.append('file', file);

                    await fetch(`${API_BASE}/api/recipients/${createdRecipients[i].id}/reports`, {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${token}` },
                        body: uploadData
                    });
                }
            }
        }

        alert('Registration successful!');
        if (role === 'doctor') {
            window.location.href = 'doctor_dashboard.html';
        } else {
            window.location.href = 'profile.html';
        }

    } catch (error) {
        console.error('Error:', error);
        alert(error.message);
    }
});

// Add new care recipient form
document.getElementById('addRecipient').addEventListener('click', () => {
    const template = document.querySelector('.care-recipient').cloneNode(true);
    template.querySelectorAll('input, select').forEach(input => input.value = '');
    template.querySelector('.remove-recipient').style.display = 'flex';
    document.getElementById('careRecipients').appendChild(template);
});

// Handle remove recipient
document.getElementById('careRecipients').addEventListener('click', (e) => {
    if (e.target.classList.contains('remove-recipient') || e.target.closest('.remove-recipient')) {
        const recipientDiv = e.target.closest('.care-recipient');
        recipientDiv.remove();
    }
});
