'use client';

import React from 'react';

const Header = () => {
    return (
        <header className="bg-[#1B4F8A] text-white p-6 md:p-10 shadow-lg text-center md:text-left">
            <div className="max-w-3xl mx-auto flex flex-col gap-1">
                <h1 className="text-2xl md:text-4xl font-extrabold tracking-tight">
                    SBI Mutual Fund
                </h1>
                <div className="flex flex-col md:flex-row md:items-baseline md:gap-3">
                    <span className="text-xl md:text-2xl font-light text-blue-100">
                        FAQ Assistant
                    </span>
                    <span className="hidden md:block text-blue-300">|</span>
                    <span className="text-sm md:text-base text-blue-200 italic opacity-80">
                        Facts only. No investment advice.
                    </span>
                </div>
            </div>
        </header>
    );
};

export default Header;
