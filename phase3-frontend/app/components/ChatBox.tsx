'use client';

import React, { useState } from 'react';

interface ChatBoxProps {
    onSubmit: (question: string) => void;
    isLoading: boolean;
}

const ChatBox: React.FC<ChatBoxProps> = ({ onSubmit, isLoading }) => {
    const [input, setInput] = useState('');
    const [warning, setWarning] = useState<string | null>(null);

    const PII_PATTERNS = {
        PAN: /[A-Z]{5}[0-9]{4}[A-Z]{1}/,
        Aadhaar: /\d{12}/,
        Phone: /[6-9]\d{9}/,
        Email: /[^@]+@[^@]+\.[^@]+/
    };

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setInput(e.target.value);
        setWarning(null);
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || isLoading) return;

        // PII Frontend Check
        const hasPII = Object.values(PII_PATTERNS).some(pattern => pattern.test(input));

        if (hasPII) {
            setWarning("Please do not enter personal information");
            return;
        }

        onSubmit(input);
        setInput('');
    };

    return (
        <div className="fixed bottom-0 left-0 right-0 p-4 bg-white border-t border-gray-200">
            <div className="max-w-3xl mx-auto">
                <form onSubmit={handleSubmit} className="relative flex items-center">
                    <input
                        type="text"
                        value={input}
                        onChange={handleInputChange}
                        placeholder="Ask a factual question..."
                        disabled={isLoading}
                        className="w-full p-4 pr-16 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#1B4F8A] disabled:bg-gray-50 transition-all"
                    />
                    <button
                        type="submit"
                        disabled={isLoading || !input.trim()}
                        className="absolute right-2 p-2 bg-[#1B4F8A] text-white rounded-lg hover:bg-[#153d6b] disabled:bg-gray-300 transition-colors w-10 h-10 flex items-center justify-center font-bold"
                        title="Send Message"
                    >
                        {isLoading ? (
                            <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                        ) : (
                            '→'
                        )}
                    </button>
                </form>
                {warning && (
                    <p className="mt-2 text-xs text-red-500 font-medium px-2">{warning}</p>
                )}
            </div>
        </div>
    );
};

export default ChatBox;
