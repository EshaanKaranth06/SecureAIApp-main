import React, { useState, useEffect } from "react";

export function MCQChallenge({ challenge, showExplanation = false }) {
    const [selectedOption, setSelectedOption] = useState(null);
    const [shouldShowExplanation, setShouldShowExplanation] = useState(showExplanation);

    // --- THIS IS THE FIX ---
    // This useEffect hook will run every time the 'challenge' prop changes.
    // When a new challenge arrives, we reset the state for the answers.
    useEffect(() => {
        setSelectedOption(null);
        setShouldShowExplanation(showExplanation);
    }, [challenge]); // The dependency array ensures this runs only when the challenge object changes

    const options = typeof challenge.options === "string"
        ? JSON.parse(challenge.options)
        : challenge.options;

    const handleOptionSelect = (index) => {
        if (selectedOption !== null) return;
        setSelectedOption(index);
        setShouldShowExplanation(true);
    };

    const getOptionClass = (index) => {
        if (selectedOption === null) {
            // Default class when no option has been selected
            return "option";
        }
        
        // If an option has been selected, determine the correct/incorrect classes
        if (index === challenge.correct_answer_id) {
            return "option correct";
        }
        if (index === selectedOption) {
            return "option incorrect";
        }

        return "option";
    };

    return (
        <div className="challenge-display">
            <p><strong>Difficulty</strong>: {challenge.difficulty}</p>
            <h3 className="challenge-title">{challenge.title}</h3>
            <div className="options">
                {options.map((option, index) => (
                    <div
                        className={getOptionClass(index)}
                        key={index}
                        onClick={() => handleOptionSelect(index)}
                    >
                        {option}
                    </div>
                ))}
            </div>
            {shouldShowExplanation && selectedOption !== null && (
                <div className="explanation">
                    <h4>Explanation</h4>
                    <p>{challenge.explanation}</p>
                </div>
            )}
        </div>
    );
}