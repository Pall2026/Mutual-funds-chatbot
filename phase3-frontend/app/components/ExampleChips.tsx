'use client';

import React from 'react';

interface ExampleChipsProps {
    onChipClick: (question: string) => void;
}

const ExampleChips: React.FC<ExampleChipsProps> = ({ onChipClick }) => {
    const examples = [
        "What is the exit load for SBI Bluechip Fund?",
        "Show me ELSS tax saver funds",
        "What is the minimum SIP amount for Flexicap?",
        "How can I download my account statement?"
    ];

    return (
        <div className="flex flex-wrap gap-2 my-4 justify-center md:justify-start">
            {examples.map((question, index) => (
                <button
                    key={index}
                    onClick={() => onChipClick(question)}
                    className="bg-[#1B4F8A] text-white px-4 py-2 rounded-full text-xs md:text-sm hover:bg-[#153d6b] transition-all whitespace-normal text-left sm:text-center active:scale-95 shadow-sm"
                >
                    {question}
                </button>
            ))}
        </div>
    );
};

export default ExampleChips;
